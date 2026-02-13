from __future__ import annotations

from datetime import date, datetime
from time import perf_counter

from app.core.config import settings
from app.schemas.contracts import DraftGenerationResponse
from app.services.evidence_validator import run_three_gates
from app.services.governance import estimate_tokens
from app.services.llm_audit import log_llm_call, reserve_budget_persistent
from app.services.pii_policy import sanitize_outbound_text
from app.services.rag_flow import decompose_requirement, merge_retrieval, retrieve_for_subrequirements
from app.services.semantic_cache import build_cache_key, get_cache, set_cache

LLM_PROVIDER = "Qwen"
LLM_MODEL = "Qwen3-Max"


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

    # Step1-3 schema-driven RAG
    sub_requirements = decompose_requirement(requirement_text)
    retrieval = retrieve_for_subrequirements(
        sub_requirements=sub_requirements,
        top_k=effective_top_k,
        industry_tag=industry_tag,
    )
    merged_evidence_ids, coverage_map, merged_hits = merge_retrieval(retrieval)

    cache_key = build_cache_key(
        industry_tag=industry_tag,
        tender_template_id=tender_template_id,
        requirement_text=requirement_text,
        evidence_ids=merged_evidence_ids,
    )
    cached = get_cache(cache_key)
    if cached:
        response = DraftGenerationResponse(**cached, cache_hit=True)
        log_llm_call(
            project_id=project_id,
            model_name=LLM_MODEL,
            purpose="SECTION_GENERATE",
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
        )
        return response

    evidence_texts = [hit.text for hit in merged_hits]
    generated_text = _compose_draft(requirement_text, evidence_texts)

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
        )

    ok, budget_remaining = reserve_budget_persistent(project_id=project_id, estimated_tokens=input_tokens + output_tokens)
    if not ok:
        log_llm_call(
            project_id=project_id,
            model_name=LLM_MODEL,
            purpose="SECTION_GENERATE",
            evidence_ids=merged_evidence_ids,
            prompt_text=requirement_text,
            input_tokens=input_tokens,
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count,
            cache_hit=False,
            pricing_blocked=False,
        )
        return DraftGenerationResponse(
            generated_text="BUDGET_EXCEEDED",
            evidence_ids=merged_evidence_ids,
            status="BUDGET_EXCEEDED",
            llm_provider=LLM_PROVIDER,
            llm_model=LLM_MODEL,
            missing_sentences=["budget_exceeded"],
            coverage=0.0,
            budget_remaining=budget_remaining,
            cache_hit=False,
            warnings=[],
            coverage_map=coverage_map,
        )

    result = run_three_gates(
        generated_text=generated_text,
        evidence_ids=merged_evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=sum(1 for ids in coverage_map.values() if ids),
        requirement_total=max(len(coverage_map), 1),
        coverage_threshold=settings.min_matrix_coverage,
    )

    warnings = _expiry_warnings([hit.payload for hit in merged_hits])

    sanitize = sanitize_outbound_text(
        text=generated_text,
        sensitive_strategy=sensitive_strategy,
        allowlist=allowlist,
    )
    if sanitize.pricing_blocked:
        log_llm_call(
            project_id=project_id,
            model_name=LLM_MODEL,
            purpose="SECTION_GENERATE",
            evidence_ids=merged_evidence_ids,
            prompt_text=requirement_text,
            input_tokens=input_tokens,
            output_tokens=0,
            latency_ms=int((perf_counter() - begin) * 1000),
            budget_remaining=budget_remaining,
            retry_count=retry_count,
            fallback_count=fallback_count,
            cache_hit=False,
            pricing_blocked=True,
        )
        return DraftGenerationResponse(
            generated_text="BLOCKED_PRICING_CONTENT",
            evidence_ids=merged_evidence_ids,
            status="BLOCKED_PRICING_CONTENT",
            llm_provider=LLM_PROVIDER,
            llm_model=LLM_MODEL,
            missing_sentences=["pricing_blocked"],
            coverage=0.0,
            budget_remaining=budget_remaining,
            cache_hit=False,
            warnings=warnings + sanitize.warnings,
            coverage_map=coverage_map,
        )

    status = result.status
    if not sanitize.text:
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("evidence_near_expiry") for w in warnings):
        status = "NEED_HUMAN_INPUT"

    response = DraftGenerationResponse(
        generated_text=sanitize.text or "NEED_HUMAN_INPUT",
        evidence_ids=merged_evidence_ids,
        status=status,
        llm_provider=LLM_PROVIDER,
        llm_model=LLM_MODEL,
        missing_sentences=result.missing_sentences,
        coverage=result.coverage,
        budget_remaining=budget_remaining,
        cache_hit=False,
        warnings=warnings + sanitize.warnings,
        coverage_map=coverage_map,
    )

    log_llm_call(
        project_id=project_id,
        model_name=LLM_MODEL,
        purpose="SECTION_GENERATE",
        evidence_ids=merged_evidence_ids,
        prompt_text=requirement_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=int((perf_counter() - begin) * 1000),
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=fallback_count,
        cache_hit=False,
        pricing_blocked=False,
    )

    if response.status == "SUPPORTED":
        set_cache(cache_key=cache_key, payload=response.model_dump(mode="json"), ttl_seconds=3600)

    return response
