from __future__ import annotations

import json
import logging
from functools import lru_cache
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_section_max_output_tokens, settings
from app.core.section_router import SectionGenerationPlan, select_generation_plan
from app.llm.model_registry import current_registry_mode
from app.schemas.contracts import DraftGenerationResponse
from app.services.adapters import AdapterUnavailableError
from app.services.byok import get_project_model_policy, resolve_profile_chain_for_task, resolve_profile_for_task
from app.services.adapters.registry import create_adapter
from app.services.context_compressor import compress_evidence_context
from app.services.evidence_validator import run_three_gates
from app.services.governance import estimate_tokens
from app.services.global_facts import detect_global_fact_conflicts, extract_global_facts_from_text
from app.services.disqualification_matrix import (
    build_matrix_from_requirements,
    check_section_against_matrix,
)
from app.services.llm_audit import log_llm_call, reserve_budget_persistent
from app.services.llm_gateway import generate_with_fallback_chain, review_with_fallback_chain
from app.services.pii_policy import sanitize_inbound_text, sanitize_outbound_text
from app.rag.rag_flow import decompose_requirement, merge_retrieval, retrieve_for_subrequirements
from app.services.semantic_cache import build_cache_key, get_cache, set_cache
from app.validator import (
    build_generation_payload,
    ensure_generation_evidence_binding,
    flatten_generation_payload,
    parse_json_payload,
    validate_generation_payload,
)


def _schema_evidence_ids(evidence_ids: list[str]) -> list[str]:
    # Schema 要求 evidence_ids 非空；检索为空时保留占位并由 gate1 判定 NEED_HUMAN_INPUT。
    return evidence_ids or ["NEED_EVIDENCE"]


def _compose_draft(
    requirement_text: str,
    evidence_texts: list[str],
    section_type: str | None = None,
) -> str:
    from app.services.fallback_templates import render_fallback_template

    effective_type = section_type if section_type else "generic"
    return render_fallback_template(
        section_type=effective_type,
        requirement_text=requirement_text,
        project_name=None,
        evidence_texts=evidence_texts,
    )


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


logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
_SECTION_ENHANCE_PROMPT_FILE = _PROMPTS_DIR / "section_enhance_r1_cn.md"


class SectionEnhanceIssue(BaseModel):
    type: str
    severity: str
    location: str
    description: str
    evidence_id: str | None = None


class SectionEnhancePayload(BaseModel):
    fixed_md: str = Field(min_length=1)
    issues: list[SectionEnhanceIssue] = Field(default_factory=list)
    passed: bool = Field(alias="pass")
    suggestions: list[str] = Field(default_factory=list)


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


@dataclass
class EnhanceStepResult:
    text: str
    payload: dict | None
    provider: str | None
    model: str | None
    fallback_index: int
    warnings: list[str]


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
        generated_text_fallback = _compose_draft(requirement_text, generation_evidence_texts) or "NEED_HUMAN_INPUT"
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


def _normalize_mode(value: str) -> str:
    return "debug" if (value or "").strip().lower() == "debug" else "prod"


def _section_context_value(section_context: dict | None, *keys: str) -> str:
    if not isinstance(section_context, dict):
        return ""
    for key in keys:
        raw = section_context.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return ""


def _section_output_limit(section_context: dict | None) -> int:
    section_type = _section_context_value(
        section_context,
        "section_type",
        "type",
        "sectionType",
        "section_kind",
    ).lower()
    return get_section_max_output_tokens(section_type or None)


def _route_warning(plan: SectionGenerationPlan) -> str:
    enhance = (
        f"{plan.post_enhance_model[0]}:{plan.post_enhance_model[1]}"
        if plan.post_enhance_model
        else "none"
    )
    return (
        "section_route:"
        f"critical={int(plan.is_critical)};"
        f"base={plan.base_model[0]}:{plan.base_model[1]};"
        f"enhance={enhance};"
        f"review={plan.review_model[0]}:{plan.review_model[1]}"
    )


def _prefer_profile_chain(profile_chain: list[object], preferred: tuple[str, str] | None) -> list[object]:
    if not preferred:
        return list(profile_chain)

    provider, model = preferred
    target_provider = provider.strip().lower()
    target_model = model.strip()
    prioritized: list[object] = []
    remainder: list[object] = []
    for item in profile_chain:
        item_provider = str(getattr(item, "provider", "")).strip().lower()
        item_model = str(getattr(item, "model", "")).strip()
        if item_provider == target_provider and item_model == target_model:
            prioritized.append(item)
        else:
            remainder.append(item)
    if not prioritized:
        return list(profile_chain)
    return [*prioritized, *remainder]


@lru_cache(maxsize=1)
def _section_enhance_prompt_template() -> str:
    if _SECTION_ENHANCE_PROMPT_FILE.exists():
        return _SECTION_ENHANCE_PROMPT_FILE.read_text(encoding="utf-8")
    return (
        "你是投标文件专家审校员。请对章节初稿做最小必要修订并输出 JSON。\\n"
        "章节标题：{section_title}\\n"
        "章节路径：{section_path}\\n"
        "章节初稿：{draft_md}\\n"
        "证据片段：{evidence_snippets}\\n"
        "约束与Schema：{json_schema}\\n"
    )


@lru_cache(maxsize=1)
def _section_enhance_schema_json() -> str:
    return json.dumps(SectionEnhancePayload.model_json_schema(by_alias=True), ensure_ascii=False)


def _render_section_enhance_prompt(
    *,
    section_title: str,
    section_path: str,
    draft_md: str,
    evidence_snippets: list[dict[str, str]],
) -> str:
    template = _section_enhance_prompt_template()
    replacements = {
        "section_title": section_title or "未命名章节",
        "section_path": section_path or section_title or "未命名章节",
        "draft_md": draft_md,
        "evidence_snippets": json.dumps(evidence_snippets, ensure_ascii=False),
        "json_schema": _section_enhance_schema_json(),
    }
    prompt = template
    for key, value in replacements.items():
        prompt = prompt.replace("{" + key + "}", str(value))
    return prompt


def _validate_section_enhance_payload(raw: str | dict) -> SectionEnhancePayload:
    payload = parse_json_payload(raw)
    try:
        return SectionEnhancePayload.model_validate(payload)
    except ValidationError as exc:
        raise ValueError("section enhance payload schema validation failed") from exc


def _enhance_with_profile(*, profile: object, prompt: str) -> SectionEnhancePayload:
    provider = str(getattr(profile, "provider", "")).strip()
    model = str(getattr(profile, "model", "")).strip()
    api_key = getattr(profile, "api_key", None)
    base_url = getattr(profile, "base_url", None)

    adapter = create_adapter(provider)
    post_chat = getattr(adapter, "_post_chat", None)
    if not callable(post_chat):
        raise AdapterUnavailableError(f"provider {provider} does not support direct chat completion")

    content = post_chat(
        model=model,
        prompt=prompt,
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )
    try:
        return _validate_section_enhance_payload(content)
    except ValueError as exc:
        raise AdapterUnavailableError(str(exc)) from exc


def _enhance_with_fallback_chain(
    *,
    profile_chain: list[object],
    prompt: str,
) -> tuple[SectionEnhancePayload, int, object]:
    last_exc: AdapterUnavailableError | None = None
    for idx, profile in enumerate(profile_chain):
        try:
            payload = _enhance_with_profile(profile=profile, prompt=prompt)
            return payload, idx, profile
        except AdapterUnavailableError as exc:
            provider = str(getattr(profile, "provider", ""))
            model = str(getattr(profile, "model", ""))
            logger.warning(
                "section enhance failed for provider=%s model=%s: %s",
                provider,
                model,
                exc,
            )
            last_exc = exc
    raise last_exc or AdapterUnavailableError("no section enhance providers available")


def _run_section_enhance_step(
    *,
    section_context: dict | None,
    plan: SectionGenerationPlan,
    review_chain: list[object],
    draft_text: str,
    evidence_texts: list[str],
    evidence_ids: list[str],
) -> EnhanceStepResult:
    if not plan.post_enhance_model:
        return EnhanceStepResult(
            text=draft_text,
            payload=None,
            provider=None,
            model=None,
            fallback_index=0,
            warnings=[],
        )

    prioritized_chain = _prefer_profile_chain(review_chain, plan.post_enhance_model)
    if not prioritized_chain:
        return EnhanceStepResult(
            text=draft_text,
            payload=None,
            provider=None,
            model=None,
            fallback_index=0,
            warnings=["enhance_chain_empty_keep_generated"],
        )

    section_title = _section_context_value(section_context, "section_title", "title")
    section_path = _section_context_value(section_context, "section_path", "chapter_path", "section_key")
    snippets: list[dict[str, str]] = []
    for idx, text in enumerate(evidence_texts[:12]):
        evidence_id = evidence_ids[idx] if idx < len(evidence_ids) else f"e-{idx + 1}"
        snippets.append({"evidence_id": evidence_id, "text": str(text).strip()})

    prompt = _render_section_enhance_prompt(
        section_title=section_title,
        section_path=section_path,
        draft_md=draft_text,
        evidence_snippets=snippets,
    )

    warnings: list[str] = []
    attempts = max(1, int(settings.task_max_retries) + 1)
    for attempt in range(1, attempts + 1):
        try:
            enhanced_payload, fallback_idx, profile = _enhance_with_fallback_chain(
                profile_chain=prioritized_chain,
                prompt=prompt,
            )
            fixed_md = enhanced_payload.fixed_md.strip() or draft_text
            if fixed_md != draft_text:
                warnings.append("enhance_applied")
            if fallback_idx > 0:
                warnings.append(f"enhance_fallback_index={fallback_idx}")
            return EnhanceStepResult(
                text=fixed_md,
                payload=enhanced_payload.model_dump(mode="json", by_alias=True),
                provider=str(getattr(profile, "provider", "")).strip() or None,
                model=str(getattr(profile, "model", "")).strip() or None,
                fallback_index=fallback_idx,
                warnings=warnings,
            )
        except AdapterUnavailableError:
            warnings.append(f"enhance_attempt_{attempt}_failed")

    warnings.append("enhance_all_providers_failed_keep_generated")
    return EnhanceStepResult(
        text=draft_text,
        payload=None,
        provider=None,
        model=None,
        fallback_index=len(prioritized_chain),
        warnings=warnings,
    )


def _run_review_step(
    *,
    review_enabled: bool,
    status: str,
    warnings: list[str],
    review_chain: list[object],
    project_id: str | None,
    draft_text: str,
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
    industry_tag: str | None = None,
    tender_template_id: str | None = None,
    sensitive_strategy: str = "mask",
    allowlist: list[str] | None = None,
    global_facts: dict | None = None,
    retry_count: int = 0,
    fallback_count: int = 0,
    section_context: dict | None = None,
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

    env_mode = _normalize_mode(current_registry_mode())
    section_plan = select_generation_plan(section_context or {}, env_mode=env_mode)
    route_warning = _route_warning(section_plan)
    section_output_limit = _section_output_limit(section_context)

    logger.info(
        "section routing resolved mode=%s section_key=%s section_title=%s critical=%s base=%s:%s enhance=%s review=%s:%s",
        env_mode,
        _section_context_value(section_context, "section_key", "id"),
        _section_context_value(section_context, "section_title", "title"),
        section_plan.is_critical,
        section_plan.base_model[0],
        section_plan.base_model[1],
        (
            f"{section_plan.post_enhance_model[0]}:{section_plan.post_enhance_model[1]}"
            if section_plan.post_enhance_model
            else "none"
        ),
        section_plan.review_model[0],
        section_plan.review_model[1],
    )

    resolved_profile = resolve_profile_for_task(project_id=project_id, task_type="GENERATE")
    gen_chain = _prefer_profile_chain(
        resolve_profile_chain_for_task(project_id=project_id, task_type="GENERATE"),
        section_plan.base_model,
    )
    review_chain = _prefer_profile_chain(
        resolve_profile_chain_for_task(project_id=project_id, task_type="REVIEW"),
        section_plan.review_model,
    )

    try:
        model_policy = get_project_model_policy(project_id) if project_id else None
    except ValueError:
        model_policy = None

    llm_provider = resolved_profile.provider
    llm_model = resolved_profile.model
    review_enabled = bool(model_policy.enable_review) if model_policy else True
    review_enabled_for_section = review_enabled or section_plan.is_critical
    cache_scope = (
        f"{tender_template_id or '_'}|p={project_id or '_'}|g={llm_provider}:{llm_model}|r={int(review_enabled_for_section)}"
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
    if cached and not review_enabled_for_section:
        cached_payload = dict(cached)
        cached_payload["cache_hit"] = True
        warnings = list(cached_payload.get("warnings") or [])
        if route_warning not in warnings:
            warnings.append(route_warning)
        cached_payload["warnings"] = warnings
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

    enhance_step = _run_section_enhance_step(
        section_context=section_context,
        plan=section_plan,
        review_chain=review_chain,
        draft_text=generation_step.generated_text,
        evidence_texts=retrieval_ctx.generation_evidence_texts,
        evidence_ids=retrieval_ctx.merged_evidence_ids,
    )
    effective_generated_text = enhance_step.text or generation_step.generated_text
    effective_output_tokens = estimate_tokens(effective_generated_text)

    if (
        generation_step.input_tokens > settings.section_max_input_tokens
        or effective_output_tokens > section_output_limit
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
                route_warning,
                *enhance_step.warnings,
                f"input_tokens={generation_step.input_tokens}",
                f"output_tokens={effective_output_tokens}",
                f"section_output_limit={section_output_limit}",
            ],
            coverage_map=retrieval_ctx.coverage_map,
            retrieval_log=retrieval_ctx.retrieval_log,
            generation_json=_safe_generation_json(generation_step.generation_payload),
        )

    ok, budget_remaining = reserve_budget_persistent(
        project_id=project_id,
        estimated_tokens=generation_step.input_tokens + effective_output_tokens,
    )
    budget_warning = "budget_exceeded_non_blocking" if not ok else None

    gate_result = run_three_gates(
        generated_text=effective_generated_text,
        evidence_ids=retrieval_ctx.merged_evidence_ids,
        evidence_texts=retrieval_ctx.evidence_texts,
        requirement_mapped=sum(1 for ids in retrieval_ctx.coverage_map.values() if ids),
        requirement_total=max(len(retrieval_ctx.coverage_map), 1),
        coverage_threshold=settings.min_matrix_coverage,
        requirement_text=requirement_text,
    )

    sanitize = sanitize_outbound_text(
        text=effective_generated_text,
        sensitive_strategy=sensitive_strategy,
        allowlist=allowlist,
    )

    if sanitize.pricing_blocked:
        total_fallbacks = fallback_count + generation_step.generation_fallback_index + enhance_step.fallback_index
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
            warnings=generation_step.warnings + [route_warning] + enhance_step.warnings + sanitize.warnings,
            coverage_map=retrieval_ctx.coverage_map,
            retrieval_log=retrieval_ctx.retrieval_log,
            generation_json=_safe_generation_json(generation_step.generation_payload),
        )

    status = gate_result.status
    global_fact_warnings = _global_fact_conflict_warnings(global_facts, effective_generated_text)
    generation_warnings = generation_step.warnings + [route_warning] + enhance_step.warnings + global_fact_warnings

    # ── Disqualification matrix soft gate (Task 18) ──
    disqualify_warnings: list[str] = []
    try:
        dq_matrix = build_matrix_from_requirements([requirement_text])
        if dq_matrix.conditions:
            dq_matrix = check_section_against_matrix(effective_generated_text, dq_matrix)
            coverage = dq_matrix.coverage_rate()
            if coverage < 1.0:
                disqualify_warnings.append(f"disqualify_matrix_coverage={coverage:.2f}")
            dq_fatal = dq_matrix.disqualify_level_missing()
            if dq_fatal:
                missing_ids = ",".join(c.condition_id for c in dq_fatal)
                disqualify_warnings.append(f"disqualify_fatal_uncovered={missing_ids}")
                status = "NEED_HUMAN_INPUT"
    except Exception:
        logger.debug("disqualification matrix check skipped due to error", exc_info=True)
    generation_warnings.extend(disqualify_warnings)

    if section_plan.is_critical and not review_enabled:
        generation_warnings.append("review_forced_by_section_routing")
    if "generate_evidence_binding_invalid" in generation_warnings:
        status = "NEED_HUMAN_INPUT"
    if not sanitize.text:
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("evidence_near_expiry") for w in generation_warnings):
        status = "NEED_HUMAN_INPUT"
    if any(w.startswith("global_facts_conflict:") for w in generation_warnings):
        status = "NEED_HUMAN_INPUT"

    review_step = _run_review_step(
        review_enabled=review_enabled_for_section,
        status=status,
        warnings=generation_warnings,
        review_chain=review_chain,
        project_id=project_id,
        draft_text=sanitize.text or effective_generated_text,
        evidence_texts=retrieval_ctx.generation_evidence_texts,
        merged_evidence_ids=retrieval_ctx.merged_evidence_ids,
        begin=begin,
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=fallback_count,
        generation_fallback_index=generation_step.generation_fallback_index,
    )

    total_fallbacks = (
        fallback_count
        + generation_step.generation_fallback_index
        + enhance_step.fallback_index
        + review_step.review_fallback_index
    )

    response = DraftGenerationResponse(
        generated_text=sanitize.text or "NEED_HUMAN_INPUT",
        evidence_ids=retrieval_ctx.merged_evidence_ids,
        status=review_step.status,
        llm_provider=llm_provider,
        llm_model=llm_model,
        missing_sentences=gate_result.missing_sentences,
        coverage=gate_result.coverage,
        budget_remaining=budget_remaining,
        cache_hit=False,
        warnings=review_step.warnings + sanitize.warnings + ([budget_warning] if budget_warning else []),
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
        output_tokens=effective_output_tokens,
        latency_ms=int((perf_counter() - begin) * 1000),
        budget_remaining=budget_remaining,
        retry_count=retry_count,
        fallback_count=total_fallbacks,
        cache_hit=False,
        pricing_blocked=False,
        blocked_reason="BUDGET_EXCEEDED" if not ok else None,
    )

    if response.status == "SUPPORTED" and not review_enabled_for_section:
        set_cache(cache_key=cache_key, payload=response.model_dump(mode="json"), ttl_seconds=3600)

    return response
