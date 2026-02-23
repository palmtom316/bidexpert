from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from time import perf_counter

from app.core.config import settings
from app.schemas.contracts import DraftGenerationResponse
from app.services.adapters import AdapterUnavailableError
from app.services.byok import get_project_model_policy, resolve_profile_chain_for_task, resolve_profile_for_task
from app.services.context_compressor import compress_evidence_context
from app.services.evidence_validator import run_three_gates
from app.services.governance import estimate_tokens
from app.services.global_facts import detect_global_fact_conflicts, extract_global_facts_from_text
from app.services.llm_audit import log_llm_call, reserve_budget_persistent
from app.services.llm_gateway import generate_with_fallback_chain, review_with_fallback_chain
from app.services.fallback_templates import render_section_fallback_template
from app.services.pii_policy import sanitize_inbound_text, sanitize_outbound_text
from app.services.review_engine import resolve_triage_gate
from app.rag.rag_flow import decompose_requirement, merge_retrieval, retrieve_for_subrequirements
from app.services.semantic_cache import build_cache_key, get_cache, set_cache
from app.validator import (
    build_generation_payload,
    ensure_generation_evidence_binding,
    flatten_generation_payload,
    validate_generation_payload,
)


def _schema_evidence_ids(evidence_ids: list[str]) -> list[str]:
    # Schema 要求 evidence_ids 非空；检索为空时保留占位并由 gate1 判定 NEED_HUMAN_INPUT。
    return evidence_ids or ["NEED_EVIDENCE"]


def _resolve_section_output_tokens(*, section_type: str | None, requirement_text: str) -> int:
    output_map = settings.section_output_tokens_map or {}
    default_limit = int(output_map.get("default", settings.section_max_output_tokens))

    normalized_section_type = (section_type or "").strip()
    if normalized_section_type and normalized_section_type in output_map:
        return max(1, int(output_map[normalized_section_type]))

    lowered_text = (requirement_text or "").lower()
    for key, value in output_map.items():
        if key == "default":
            continue
        normalized_key = str(key).strip()
        if not normalized_key:
            continue
        if normalized_key in requirement_text or normalized_key.lower() in lowered_text:
            return max(1, int(value))

    return max(1, default_limit)


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


def _safe_generation_json(payload) -> dict:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(mode="json")
    return dict(payload)


@dataclass
class RetrievalContext:
    retrieval_log: list[dict]
    merged_evidence_ids: list[str]
    coverage_map: dict[str, list[str]]
    merged_hits: list[object]
    evidence_texts: list[str]
    generation_evidence_texts: list[str]
    top_chunks: list[dict]
    warnings: list[str]


@dataclass
class GenerationStepResult:
    generation_payload: object
    generated_text: str
    llm_provider: str
    llm_model: str
    generation_fallback_index: int
    input_tokens: int
    output_tokens: int
    warnings: list[str]


@dataclass
class ReviewStepResult:
    status: str
    warnings: list[str]
    review_report: dict | None
    review_fallback_index: int


def _blocked_pricing_response(warnings: list[str]) -> DraftGenerationResponse:
    return DraftGenerationResponse(
        generated_text="BLOCKED_PRICING_CONTENT",
        evidence_ids=[],
        status="BLOCKED_PRICING_CONTENT",
        missing_sentences=["pricing_blocked"],
        coverage=0.0,
        warnings=warnings,
        coverage_map={},
        retrieval_log=[],
        generation_json={},
        review_json=None,
    )


def _build_retrieval_context(
    *,
    requirement_text: str,
    effective_top_k: int,
    industry_tag: str | None,
    project_id: str | None,
) -> RetrievalContext:
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

    evidence_texts: list[str] = []
    top_chunks: list[dict] = []
    for hit in merged_hits:
        parent_context = str(hit.payload.get("parent_context", "") or "").strip()
        snippet = parent_context or hit.text
        evidence_texts.append(snippet)
        top_chunks.append(
            {
                "chunk_id": hit.chunk_id,
                "text": hit.text,
                "parent_context": parent_context,
                "payload": hit.payload,
            }
        )
    compressed_context = compress_evidence_context(requirement_text=requirement_text, evidence_texts=evidence_texts)
    generation_evidence_texts = compressed_context.evidence_texts

    warnings = _expiry_warnings([hit.payload for hit in merged_hits])
    if compressed_context.compressed:
        warnings.append(
            f"context_compressed:{compressed_context.original_chars}->{compressed_context.compressed_chars}"
        )
        if compressed_context.dropped_count > 0:
            warnings.append(f"context_compression_dropped={compressed_context.dropped_count}")

    return RetrievalContext(
        retrieval_log=retrieval_log,
        merged_evidence_ids=merged_evidence_ids,
        coverage_map=coverage_map,
        merged_hits=merged_hits,
        evidence_texts=evidence_texts,
        generation_evidence_texts=generation_evidence_texts,
        top_chunks=top_chunks,
        warnings=warnings,
    )


def _run_generation_step(
    *,
    gen_chain: list[object],
    project_id: str | None,
    requirement_text: str,
    section_type: str | None,
    generation_evidence_texts: list[str],
    merged_evidence_ids: list[str],
    top_chunks: list[dict],
    global_facts: dict | None,
    llm_provider: str,
    llm_model: str,
    warnings: list[str],
) -> GenerationStepResult:
    next_warnings = list(warnings)
    generation_fallback_index = 0
    generation_payload = build_generation_payload("NEED_HUMAN_INPUT", _schema_evidence_ids(merged_evidence_ids))
    try:
        generated, generation_fallback_index = generate_with_fallback_chain(
            profile_chain=gen_chain,
            project_id=project_id,
            requirement_text=requirement_text,
            section_type=section_type,
            evidence_texts=generation_evidence_texts,
            evidence_ids=merged_evidence_ids,
            global_facts=global_facts,
            relevant_requirements=[requirement_text],
            relevant_scoring=[],
            top_chunks=top_chunks,
        )
        llm_provider = generated.provider
        llm_model = generated.model
        if generation_fallback_index > 0:
            next_warnings.append(f"generate_fallback_index={generation_fallback_index}")
        try:
            if generated.content_json:
                generation_payload = ensure_generation_evidence_binding(
                    validate_generation_payload(generated.content_json),
                    allowed_evidence_ids=merged_evidence_ids,
                )
            else:
                generation_payload = build_generation_payload(generated.text, _schema_evidence_ids(merged_evidence_ids))
                next_warnings.append("generate_schema_wrapped_from_text")
        except ValueError as exc:
            generation_payload = build_generation_payload("NEED_HUMAN_INPUT", _schema_evidence_ids(merged_evidence_ids))
            if "unknown evidence_ids" in str(exc):
                next_warnings.append("generate_evidence_binding_invalid")
            else:
                next_warnings.append("generate_schema_validation_failed")
    except AdapterUnavailableError:
        generation_fallback_index = len(gen_chain)
        generated_text_fallback = render_section_fallback_template(
            requirement_text=requirement_text,
            evidence_texts=generation_evidence_texts,
            section_type=section_type,
        )
        generation_payload = build_generation_payload(generated_text_fallback, _schema_evidence_ids(merged_evidence_ids))
        next_warnings.append("generate_all_providers_failed_local_template")

    generated_text = flatten_generation_payload(generation_payload)
    input_tokens = estimate_tokens(requirement_text + "\n" + "\n".join(generation_evidence_texts))
    output_tokens = estimate_tokens(generated_text)

    return GenerationStepResult(
        generation_payload=generation_payload,
        generated_text=generated_text,
        llm_provider=llm_provider,
        llm_model=llm_model,
        generation_fallback_index=generation_fallback_index,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        warnings=next_warnings,
    )


def _global_fact_conflict_warnings(global_facts: dict | None, generated_text: str) -> list[str]:
    if not global_facts:
        return []
    try:
        candidate = extract_global_facts_from_text(generated_text)
    except ValueError:
        return []
    conflicts = detect_global_fact_conflicts(global_facts, candidate)
    return [f"global_facts_conflict:{field}" for field in conflicts]


def _review_status_hint(review_report: dict | None, fallback_status: str) -> str:
    if isinstance(review_report, dict):
        raw_status = review_report.get("status")
        if isinstance(raw_status, str) and raw_status.strip():
            return raw_status.strip().upper()
        raw_approved = review_report.get("approved")
        if isinstance(raw_approved, bool):
            return "PASS" if raw_approved else "REWRITE"
    return "PASS" if fallback_status == "SUPPORTED" else "WARN"


def _disqualify_coverage_ok(review_report: dict | None, warnings: list[str]) -> bool:
    joined_warnings = " ".join(str(item).lower() for item in warnings)
    if "disqualify" in joined_warnings and ("missing" in joined_warnings or "not_covered" in joined_warnings):
        return False
    if "废标" in joined_warnings and "缺失" in joined_warnings:
        return False
    if not isinstance(review_report, dict):
        return True
    for key in ("disqualify_clause_coverage", "disqualify_coverage", "disqualify_covered"):
        if key not in review_report:
            continue
        value = review_report.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return float(value) >= 1.0
    issues = review_report.get("issues", [])
    if isinstance(issues, list):
        issue_text = " ".join(str(item).lower() for item in issues)
        if "disqualify" in issue_text and ("missing" in issue_text or "not_covered" in issue_text):
            return False
        if "废标" in issue_text and "缺失" in issue_text:
            return False
    return True


def _run_review_step(
    *,
    review_enabled: bool,
    status: str,
    warnings: list[str],
    review_chain: list[object],
    project_id: str | None,
    draft_text: str,
    section_type: str | None,
    evidence_texts: list[str],
    merged_evidence_ids: list[str],
    begin: float,
    budget_remaining: int | None,
    retry_count: int,
    fallback_count: int,
    generation_fallback_index: int,
) -> ReviewStepResult:
    next_status = status
    next_warnings = list(warnings)
    review_fallback_index = 0
    review_issues: list[str] = []
    review_report: dict | None = None

    if not review_enabled:
        return ReviewStepResult(
            status=next_status,
            warnings=next_warnings,
            review_report=review_report,
            review_fallback_index=review_fallback_index,
        )

    try:
        review_result, review_fallback_index = review_with_fallback_chain(
            profile_chain=review_chain,
            project_id=project_id,
            draft_text=draft_text,
            section_type=section_type,
            evidence_texts=evidence_texts,
        )
        review_report = review_result.report
        if review_fallback_index > 0:
            next_warnings.append(f"review_fallback_index={review_fallback_index}")
        if not review_result.approved:
            next_status = "NEED_HUMAN_INPUT"
            review_issues = review_result.issues or ["review_rejected"]
            next_warnings.extend([f"review_issue:{item}" for item in review_issues])
        review_profile_id = None
        if 0 <= review_fallback_index < len(review_chain):
            review_profile_id = review_chain[review_fallback_index].profile_id
        log_llm_call(
            project_id=project_id,
            model_name=review_result.model,
            purpose="SECTION_REVIEW",
            provider_profile_id=review_profile_id,
            evidence_ids=merged_evidence_ids,
            prompt_text=draft_text,
            input_tokens=estimate_tokens(draft_text),
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count + generation_fallback_index + review_fallback_index,
            cache_hit=False,
            pricing_blocked=False,
            blocked_reason="REVIEW_REJECTED" if review_issues else None,
        )
    except AdapterUnavailableError:
        review_fallback_index = len(review_chain)
        next_warnings.append("review_all_providers_failed_local_validator")
        next_status = "NEED_HUMAN_INPUT"
        review_report = {
            "missing_requirements": [],
            "logical_inconsistencies": [],
            "risk_points": ["review_all_providers_failed"],
            "coverage_estimate": 0.0,
            "score_estimate": 0.0,
            "approved": False,
            "issues": ["review_all_providers_failed"],
        }
        log_llm_call(
            project_id=project_id,
            model_name=review_chain[0].model if review_chain else "unknown",
            purpose="SECTION_REVIEW",
            provider_profile_id=review_chain[0].profile_id if review_chain else None,
            evidence_ids=merged_evidence_ids,
            prompt_text=draft_text,
            input_tokens=estimate_tokens(draft_text),
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count + generation_fallback_index + review_fallback_index,
            cache_hit=False,
            pricing_blocked=False,
            blocked_reason="REVIEW_ALL_PROVIDERS_FAILED",
        )

    return ReviewStepResult(
        status=next_status,
        warnings=next_warnings,
        review_report=review_report,
        review_fallback_index=review_fallback_index,
    )


def generate_draft_with_retrieval(
    requirement_id: str,
    requirement_text: str,
    top_k: int = 5,
    project_id: str | None = None,
    section_type: str | None = None,
    industry_tag: str | None = None,
    tender_template_id: str | None = None,
    sensitive_strategy: str = "mask",
    allowlist: list[str] | None = None,
    global_facts: dict | None = None,
    retry_count: int = 0,
    fallback_count: int = 0,
) -> DraftGenerationResponse:
    del requirement_id

    begin = perf_counter()
    effective_top_k = max(
        int(settings.qdrant_prompt_topn_min),
        min(int(top_k), int(settings.qdrant_prompt_topn_max)),
    )

    inbound_result = sanitize_inbound_text(requirement_text)
    if inbound_result.pricing_blocked:
        return _blocked_pricing_response(inbound_result.warnings)
    requirement_text = inbound_result.text
    if global_facts is None:
        try:
            global_facts = extract_global_facts_from_text(requirement_text)
        except ValueError:
            global_facts = {}

    resolved_profile = resolve_profile_for_task(project_id=project_id, task_type="GENERATE")
    gen_chain = resolve_profile_chain_for_task(project_id=project_id, task_type="GENERATE")
    review_chain = resolve_profile_chain_for_task(project_id=project_id, task_type="REVIEW")

    try:
        model_policy = get_project_model_policy(project_id) if project_id else None
    except ValueError:
        model_policy = None

    llm_provider = resolved_profile.provider
    llm_model = resolved_profile.model
    review_enabled = bool(model_policy.enable_review) if model_policy else True
    cache_scope = (
        f"{tender_template_id or '_'}|p={project_id or '_'}|g={llm_provider}:{llm_model}|r={int(review_enabled)}"
    )

    retrieval_ctx = _build_retrieval_context(
        requirement_text=requirement_text,
        effective_top_k=effective_top_k,
        industry_tag=industry_tag,
        project_id=project_id,
    )

    cache_key = build_cache_key(
        industry_tag=industry_tag,
        tender_template_id=cache_scope,
        requirement_text=requirement_text,
        evidence_ids=retrieval_ctx.merged_evidence_ids,
    )
    cached = get_cache(cache_key)
    if cached and not review_enabled:
        cached_payload = dict(cached)
        cached_payload["cache_hit"] = True
        response = DraftGenerationResponse(**cached_payload)
        response.llm_provider = llm_provider
        response.llm_model = llm_model
        if not response.retrieval_log:
            response.retrieval_log = retrieval_ctx.retrieval_log
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

    generation_step = _run_generation_step(
        gen_chain=gen_chain,
        project_id=project_id,
        requirement_text=requirement_text,
        section_type=section_type,
        generation_evidence_texts=retrieval_ctx.generation_evidence_texts,
        merged_evidence_ids=retrieval_ctx.merged_evidence_ids,
        top_chunks=retrieval_ctx.top_chunks,
        global_facts=global_facts,
        llm_provider=llm_provider,
        llm_model=llm_model,
        warnings=retrieval_ctx.warnings,
    )
    llm_provider = generation_step.llm_provider
    llm_model = generation_step.llm_model

    section_output_limit = _resolve_section_output_tokens(
        section_type=section_type,
        requirement_text=requirement_text,
    )
    if (
        generation_step.input_tokens > settings.section_max_input_tokens
        or generation_step.output_tokens > section_output_limit
    ):
        return DraftGenerationResponse(
            generated_text="NEED_HUMAN_INPUT",
            evidence_ids=retrieval_ctx.merged_evidence_ids,
            status="NEED_HUMAN_INPUT",
            llm_provider=llm_provider,
            llm_model=llm_model,
            missing_sentences=["section_token_limit_exceeded"],
            coverage=0.0,
            budget_remaining=None,
            cache_hit=False,
            warnings=[
                *generation_step.warnings,
                f"input_tokens={generation_step.input_tokens}",
                f"output_tokens={generation_step.output_tokens}",
                f"section_output_limit={section_output_limit}",
            ],
            coverage_map=retrieval_ctx.coverage_map,
            retrieval_log=retrieval_ctx.retrieval_log,
            generation_json=_safe_generation_json(generation_step.generation_payload),
        )

    ok, budget_remaining = reserve_budget_persistent(
        project_id=project_id,
        estimated_tokens=generation_step.input_tokens + generation_step.output_tokens,
    )
    budget_warning = "budget_exceeded_non_blocking" if not ok else None

    gate_result = run_three_gates(
        generated_text=generation_step.generated_text,
        evidence_ids=retrieval_ctx.merged_evidence_ids,
        evidence_texts=retrieval_ctx.evidence_texts,
        requirement_mapped=sum(1 for ids in retrieval_ctx.coverage_map.values() if ids),
        requirement_total=max(len(retrieval_ctx.coverage_map), 1),
        coverage_threshold=settings.min_matrix_coverage,
        requirement_text=requirement_text,
    )

    sanitize = sanitize_outbound_text(
        text=generation_step.generated_text,
        sensitive_strategy=sensitive_strategy,
        allowlist=allowlist,
    )

    if sanitize.pricing_blocked:
        total_fallbacks = fallback_count + generation_step.generation_fallback_index
        log_llm_call(
            project_id=project_id,
            model_name=llm_model,
            purpose="SECTION_GENERATE",
            provider_profile_id=resolved_profile.profile_id,
            evidence_ids=retrieval_ctx.merged_evidence_ids,
            prompt_text=requirement_text,
            input_tokens=generation_step.input_tokens,
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=total_fallbacks,
            cache_hit=False,
            pricing_blocked=True,
            blocked_reason="PRICING_BLOCKED",
        )
        return DraftGenerationResponse(
            generated_text="BLOCKED_PRICING_CONTENT",
            evidence_ids=retrieval_ctx.merged_evidence_ids,
            status="BLOCKED_PRICING_CONTENT",
            llm_provider=llm_provider,
            llm_model=llm_model,
            missing_sentences=["pricing_blocked"],
            coverage=0.0,
            budget_remaining=budget_remaining,
            cache_hit=False,
            warnings=generation_step.warnings + sanitize.warnings,
            coverage_map=retrieval_ctx.coverage_map,
            retrieval_log=retrieval_ctx.retrieval_log,
            generation_json=_safe_generation_json(generation_step.generation_payload),
        )

    status = gate_result.status
    global_fact_warnings = _global_fact_conflict_warnings(global_facts, generation_step.generated_text)
    generation_warnings = generation_step.warnings + global_fact_warnings
    if "generate_evidence_binding_invalid" in generation_warnings:
        status = "NEED_HUMAN_INPUT"
    if not sanitize.text:
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("evidence_near_expiry") for w in generation_warnings):
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("global_facts_conflict:") for w in generation_warnings):
        status = "NEED_HUMAN_INPUT"

    review_step = _run_review_step(
        review_enabled=review_enabled,
        status=status,
        warnings=generation_warnings,
        review_chain=review_chain,
        project_id=project_id,
        draft_text=sanitize.text or generation_step.generated_text,
        section_type=section_type,
        evidence_texts=retrieval_ctx.generation_evidence_texts,
        merged_evidence_ids=retrieval_ctx.merged_evidence_ids,
        begin=begin,
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=fallback_count,
        generation_fallback_index=generation_step.generation_fallback_index,
    )
    triage_gate = resolve_triage_gate(
        review_status=_review_status_hint(review_step.review_report, review_step.status),
        review_report=review_step.review_report,
        warnings=review_step.warnings,
        disqualify_coverage_ok=_disqualify_coverage_ok(review_step.review_report, review_step.warnings),
    )
    final_status = review_step.status
    triage_warnings: list[str] = []
    if triage_gate != "PASS":
        final_status = "NEED_HUMAN_INPUT"
        triage_warnings.append(f"review_gate:{triage_gate}")

    total_fallbacks = fallback_count + generation_step.generation_fallback_index + review_step.review_fallback_index

    response = DraftGenerationResponse(
        generated_text=sanitize.text or "NEED_HUMAN_INPUT",
        evidence_ids=retrieval_ctx.merged_evidence_ids,
        status=final_status,
        review_gate=triage_gate,
        llm_provider=llm_provider,
        llm_model=llm_model,
        missing_sentences=gate_result.missing_sentences,
        coverage=gate_result.coverage,
        budget_remaining=budget_remaining,
        cache_hit=False,
        warnings=review_step.warnings + triage_warnings + sanitize.warnings + ([budget_warning] if budget_warning else []),
        coverage_map=retrieval_ctx.coverage_map,
        retrieval_log=retrieval_ctx.retrieval_log,
        generation_json=_safe_generation_json(generation_step.generation_payload),
        review_json=review_step.review_report,
    )

    log_llm_call(
        project_id=project_id,
        model_name=llm_model,
        purpose="SECTION_GENERATE",
        provider_profile_id=resolved_profile.profile_id,
        evidence_ids=retrieval_ctx.merged_evidence_ids,
        prompt_text=requirement_text,
        input_tokens=generation_step.input_tokens,
        output_tokens=generation_step.output_tokens,
        latency_ms=int((perf_counter() - begin) * 1000),
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=total_fallbacks,
        cache_hit=False,
        pricing_blocked=False,
        blocked_reason="BUDGET_EXCEEDED" if not ok else None,
    )

    if response.status == "SUPPORTED" and not review_enabled:
        set_cache(cache_key=cache_key, payload=response.model_dump(mode="json"), ttl_seconds=3600)

    return response
