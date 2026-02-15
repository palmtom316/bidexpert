from __future__ import annotations

from datetime import date, datetime
from time import perf_counter

from app.core.config import settings
from app.schemas.contracts import DraftGenerationResponse
from app.services.byok import get_project_model_policy, resolve_profile_for_task
from app.services.adapters import AdapterUnavailableError
from app.services.evidence_validator import run_three_gates
from app.services.governance import estimate_tokens
from app.services.llm_gateway import generate_with_profile, review_with_profile
from app.services.llm_audit import log_llm_call, reserve_budget_persistent
from app.services.pii_policy import sanitize_outbound_text
from app.services.rag_flow import decompose_requirement, merge_retrieval, retrieve_for_subrequirements
from app.services.semantic_cache import build_cache_key, get_cache, set_cache
from app.validator import build_generation_payload, flatten_generation_payload, validate_generation_payload


def _schema_evidence_ids(evidence_ids: list[str]) -> list[str]:
    # Schema 要求 evidence_ids 非空；检索为空时保留占位并由 gate1 判定 NEED_HUMAN_INPUT。
    return evidence_ids or ["NEED_EVIDENCE"]


def _compose_draft(requirement_text: str, evidence_texts: list[str]) -> str:
    if not evidence_texts:
        return ""
    snippets = [text.strip().split("。", maxsplit=1)[0] for text in evidence_texts if text.strip()]
    if not snippets:
        return ""
    return f"针对要求“{requirement_text}”，我们具备以下能力：" + "；".join(snippets[:3]) + "。"


def _expiry_warnings(payloads: list[dict]) -> list[str]:
    warnings: list[str] = []
    today = date.today()
    for payload in payloads:
        valid_to = payload.get("valid_to")
        if not valid_to:
            continue
        try:
            expire_date = datetime.strptime(valid_to, "%Y-%m-%d").date()
        except ValueError:
            continue

        days_left = (expire_date - today).days
        if days_left < 0:
            warnings.append(f"evidence_expired:{payload.get('chunk_id')}")
        elif days_left <= settings.evidence_expiry_warning_days:
            warnings.append(f"evidence_near_expiry:{payload.get('chunk_id')}:{days_left}d")
    return warnings


def generate_draft_with_retrieval(
    requirement_id: str,
    requirement_text: str,
    top_k: int = 5,
    project_id: str | None = None,
    industry_tag: str | None = None,
    tender_template_id: str | None = None,
    sensitive_strategy: str = "mask",
    allowlist: list[str] | None = None,
    retry_count: int = 0,
    fallback_count: int = 0,
) -> DraftGenerationResponse:
    begin = perf_counter()
    effective_top_k = max(1, min(top_k, 8))
    resolved_profile = resolve_profile_for_task(project_id=project_id, task_type="GENERATE")
    review_profile = resolve_profile_for_task(project_id=project_id, task_type="REVIEW")
    try:
        model_policy = get_project_model_policy(project_id) if project_id else None
    except ValueError:
        model_policy = None
    llm_provider = resolved_profile.provider
    llm_model = resolved_profile.model
    review_enabled = bool(model_policy.enable_review) if model_policy else True
    cache_scope = f"{tender_template_id or '_'}|p={project_id or '_'}|g={llm_provider}:{llm_model}|r={int(review_enabled)}"

    # Step1-3 schema-driven RAG
    sub_requirements = decompose_requirement(requirement_text)
    retrieval_result = retrieve_for_subrequirements(
        sub_requirements=sub_requirements,
        top_k=effective_top_k,
        industry_tag=industry_tag,
        project_id=project_id,
    )
    if isinstance(retrieval_result, tuple):
        retrieval, retrieval_log = retrieval_result
    else:
        retrieval, retrieval_log = retrieval_result, []
    merged_evidence_ids, coverage_map, merged_hits = merge_retrieval(retrieval)

    cache_key = build_cache_key(
        industry_tag=industry_tag,
        tender_template_id=cache_scope,
        requirement_text=requirement_text,
        evidence_ids=merged_evidence_ids,
    )
    cached = get_cache(cache_key)
    if cached and not review_enabled:
        cached_payload = dict(cached)
        cached_payload["cache_hit"] = True
        response = DraftGenerationResponse(**cached_payload)
        response.llm_provider = llm_provider
        response.llm_model = llm_model
        if not response.retrieval_log:
            response.retrieval_log = retrieval_log
        log_llm_call(
            project_id=project_id,
            model_name=llm_model,
            purpose="SECTION_GENERATE",
            provider_profile_id=resolved_profile.profile_id,
            evidence_ids=response.evidence_ids,
            prompt_text=requirement_text,
            input_tokens=estimate_tokens(requirement_text),
            output_tokens=estimate_tokens(response.generated_text),
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=response.budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count,
            cache_hit=True,
            pricing_blocked=False,
            blocked_reason=None,
        )
        return response

    evidence_texts = [hit.text for hit in merged_hits]
    warnings = _expiry_warnings([hit.payload for hit in merged_hits])
    generation_fallback = False
    generation_payload = build_generation_payload("NEED_HUMAN_INPUT", _schema_evidence_ids(merged_evidence_ids))
    try:
        generated = generate_with_profile(
            provider=llm_provider,
            model=llm_model,
            api_key=resolved_profile.api_key,
            base_url=resolved_profile.base_url,
            requirement_text=requirement_text,
            evidence_texts=evidence_texts,
            evidence_ids=merged_evidence_ids,
        )
        try:
            if generated.content_json:
                generation_payload = validate_generation_payload(generated.content_json)
            else:
                generation_payload = build_generation_payload(generated.text, _schema_evidence_ids(merged_evidence_ids))
                warnings.append("generate_schema_wrapped_from_text")
        except ValueError:
            generation_payload = build_generation_payload("NEED_HUMAN_INPUT", _schema_evidence_ids(merged_evidence_ids))
            warnings.append("generate_schema_validation_failed")
    except AdapterUnavailableError:
        generation_fallback = True
        generated_text_fallback = _compose_draft(requirement_text, evidence_texts) or "NEED_HUMAN_INPUT"
        generation_payload = build_generation_payload(generated_text_fallback, _schema_evidence_ids(merged_evidence_ids))
        warnings.append("generate_fallback_local_template")
    generated_text = flatten_generation_payload(generation_payload)

    input_tokens = estimate_tokens(requirement_text + "\n" + "\n".join(evidence_texts))
    output_tokens = estimate_tokens(generated_text)
    if input_tokens > settings.section_max_input_tokens or output_tokens > settings.section_max_output_tokens:
        return DraftGenerationResponse(
            generated_text="NEED_HUMAN_INPUT",
            evidence_ids=merged_evidence_ids,
            status="NEED_HUMAN_INPUT",
            missing_sentences=["section_token_limit_exceeded"],
            coverage=0.0,
            budget_remaining=None,
            cache_hit=False,
            warnings=[f"input_tokens={input_tokens}", f"output_tokens={output_tokens}"],
            coverage_map=coverage_map,
            retrieval_log=retrieval_log,
            generation_json=generation_payload.model_dump(mode="json"),
        )

    ok, budget_remaining = reserve_budget_persistent(project_id=project_id, estimated_tokens=input_tokens + output_tokens)
    budget_warning = "budget_exceeded_non_blocking" if not ok else None

    result = run_three_gates(
        generated_text=generated_text,
        evidence_ids=merged_evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=sum(1 for ids in coverage_map.values() if ids),
        requirement_total=max(len(coverage_map), 1),
        coverage_threshold=settings.min_matrix_coverage,
        requirement_text=requirement_text,
    )

    sanitize = sanitize_outbound_text(
        text=generated_text,
        sensitive_strategy=sensitive_strategy,
        allowlist=allowlist,
    )
    if sanitize.pricing_blocked:
        log_llm_call(
            project_id=project_id,
            model_name=llm_model,
            purpose="SECTION_GENERATE",
            provider_profile_id=resolved_profile.profile_id,
            evidence_ids=merged_evidence_ids,
            prompt_text=requirement_text,
            input_tokens=input_tokens,
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count + (1 if generation_fallback else 0),
            cache_hit=False,
            pricing_blocked=True,
            blocked_reason="PRICING_BLOCKED",
        )
        return DraftGenerationResponse(
            generated_text="BLOCKED_PRICING_CONTENT",
            evidence_ids=merged_evidence_ids,
            status="BLOCKED_PRICING_CONTENT",
            llm_provider=llm_provider,
            llm_model=llm_model,
            missing_sentences=["pricing_blocked"],
            coverage=0.0,
            budget_remaining=budget_remaining,
            cache_hit=False,
            warnings=warnings + sanitize.warnings,
            coverage_map=coverage_map,
            retrieval_log=retrieval_log,
            generation_json=generation_payload.model_dump(mode="json"),
        )

    status = result.status
    if not sanitize.text:
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("evidence_near_expiry") for w in warnings):
        status = "NEED_HUMAN_INPUT"

    review_fallback = False
    review_provider_fallback = False
    review_issues: list[str] = []
    review_report: dict | None = None
    if review_enabled:
        try:
            review_result = review_with_profile(
                provider=review_profile.provider,
                model=review_profile.model,
                api_key=review_profile.api_key,
                base_url=review_profile.base_url,
                draft_text=sanitize.text or generated_text,
                evidence_texts=evidence_texts,
            )
            review_report = review_result.report
            if not review_result.approved:
                status = "NEED_HUMAN_INPUT"
                review_issues = review_result.issues or ["review_rejected"]
                warnings.extend([f"review_issue:{item}" for item in review_issues])
            log_llm_call(
                project_id=project_id,
                model_name=review_result.model,
                purpose="SECTION_REVIEW",
                provider_profile_id=review_profile.profile_id,
                evidence_ids=merged_evidence_ids,
                prompt_text=sanitize.text or generated_text,
                input_tokens=estimate_tokens(sanitize.text or generated_text),
                output_tokens=0,
                latency_ms=int((perf_counter() - begin) * 1000),
                budget_remaining=budget_remaining,
                retry_count=retry_count,
                fallback_count=fallback_count,
                cache_hit=False,
                pricing_blocked=False,
                blocked_reason="REVIEW_REJECTED" if review_issues else None,
            )
        except AdapterUnavailableError:
            fallback_provider = (settings.review_fallback_provider or "").strip().lower()
            fallback_model = (settings.review_fallback_model or "").strip()
            if fallback_provider and fallback_model:
                try:
                    fallback_review = review_with_profile(
                        provider=fallback_provider,
                        model=fallback_model,
                        api_key=settings.review_fallback_api_key,
                        base_url=settings.review_fallback_base_url,
                        draft_text=sanitize.text or generated_text,
                        evidence_texts=evidence_texts,
                    )
                    review_provider_fallback = True
                    warnings.append("review_fallback_provider_used")
                    review_report = fallback_review.report
                    if not fallback_review.approved:
                        status = "NEED_HUMAN_INPUT"
                        review_issues = fallback_review.issues or ["review_rejected"]
                        warnings.extend([f"review_issue:{item}" for item in review_issues])
                    log_llm_call(
                        project_id=project_id,
                        model_name=fallback_review.model,
                        purpose="SECTION_REVIEW",
                        provider_profile_id=review_profile.profile_id,
                        evidence_ids=merged_evidence_ids,
                        prompt_text=sanitize.text or generated_text,
                        input_tokens=estimate_tokens(sanitize.text or generated_text),
                        output_tokens=0,
                        latency_ms=int((perf_counter() - begin) * 1000),
                        budget_remaining=budget_remaining,
                        retry_count=retry_count,
                        fallback_count=fallback_count + 1,
                        cache_hit=False,
                        pricing_blocked=False,
                        blocked_reason="REVIEW_FALLBACK_PROVIDER" if review_issues else None,
                    )
                except AdapterUnavailableError:
                    review_fallback = True
                    warnings.append("review_fallback_local_validator")
            else:
                review_fallback = True
                warnings.append("review_fallback_local_validator")

            if review_fallback:
                review_report = {
                    "missing_requirements": [],
                    "logical_inconsistencies": [],
                    "risk_points": ["review_fallback_local_validator"],
                    "coverage_estimate": 0.0,
                    "score_estimate": 0.0,
                    "approved": False,
                    "issues": ["review_fallback_local_validator"],
                }
                log_llm_call(
                    project_id=project_id,
                    model_name=review_profile.model,
                    purpose="SECTION_REVIEW",
                    provider_profile_id=review_profile.profile_id,
                    evidence_ids=merged_evidence_ids,
                    prompt_text=sanitize.text or generated_text,
                    input_tokens=estimate_tokens(sanitize.text or generated_text),
                    output_tokens=0,
                    latency_ms=int((perf_counter() - begin) * 1000),
                    budget_remaining=budget_remaining,
                    retry_count=retry_count,
                    fallback_count=fallback_count + 1,
                    cache_hit=False,
                    pricing_blocked=False,
                    blocked_reason="REVIEW_FALLBACK_LOCAL_ONLY",
                )

    response = DraftGenerationResponse(
        generated_text=sanitize.text or "NEED_HUMAN_INPUT",
        evidence_ids=merged_evidence_ids,
        status=status,
        llm_provider=llm_provider,
        llm_model=llm_model,
        missing_sentences=result.missing_sentences,
        coverage=result.coverage,
        budget_remaining=budget_remaining,
        cache_hit=False,
        warnings=warnings + sanitize.warnings + ([budget_warning] if budget_warning else []),
        coverage_map=coverage_map,
        retrieval_log=retrieval_log,
        generation_json=generation_payload.model_dump(mode="json"),
        review_json=review_report,
    )

    log_llm_call(
        project_id=project_id,
        model_name=llm_model,
        purpose="SECTION_GENERATE",
        provider_profile_id=resolved_profile.profile_id,
        evidence_ids=merged_evidence_ids,
        prompt_text=requirement_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((perf_counter() - begin) * 1000),
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=fallback_count + (1 if generation_fallback or review_fallback or review_provider_fallback else 0),
        cache_hit=False,
        pricing_blocked=False,
        blocked_reason="BUDGET_EXCEEDED" if not ok else None,
    )

    if response.status == "SUPPORTED" and not review_enabled:
        set_cache(cache_key=cache_key, payload=response.model_dump(mode="json"), ttl_seconds=3600)

    return response
