from __future__ import annotations

import uuid
import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.core.pricing import get_estimated_cost
from app.db.session import get_db
from app.models.tables import AuditLog, Document, EvidenceChunk, ExpertDoc, KBIngestRun, KBIngestStep, LLMCallLog
from app.services.expert_library import (
    get_expert_library_go_live_thresholds,
    get_expert_library_thresholds,
    publish_expert_library_go_live_thresholds,
    update_expert_library_go_live_thresholds,
    update_expert_library_thresholds,
)

router = APIRouter()


class ModelUsageStats(BaseModel):
    model_name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    call_count: int
    estimated_cost: float
    currency: str


class UsageStatsResponse(BaseModel):
    items: list[ModelUsageStats]
    total_cost_usd: float


class ExpertQualityStats(BaseModel):
    doc_count: int
    chunk_count: int
    avg_quality_score: float
    low_quality_chunk_count: int
    low_quality_rate: float
    pricing_related_chunk_count: int
    kb_ready_count: int
    kb_failed_count: int
    low_quality_threshold: float
    schema_pass_rate: float = 0.0
    key_field_completeness_rate: float = 0.0
    fallback_trigger_rate: float = 0.0
    manual_review_rate: float = 0.0
    evidence_coverage_rate: float = 0.0


class ExpertQualityStatsResponse(BaseModel):
    project_id: str | None = None
    industry_tag: str | None = None
    stats: ExpertQualityStats
    thresholds: dict[str, float]
    threshold_source: dict = Field(default_factory=dict)


class ExpertModelCompareItem(BaseModel):
    model_name: str
    purpose: str
    call_count: int
    success_rate: float
    fallback_rate: float
    cache_hit_rate: float
    avg_latency_ms: float
    avg_input_tokens: float
    avg_output_tokens: float
    avg_total_tokens: float
    estimated_cost_usd: float = 0.0
    failure_count: int = 0
    top_failure_type: str | None = None


class ExpertModelCompareResponse(BaseModel):
    project_id: str | None = None
    days: int
    items: list[ExpertModelCompareItem]


class ExpertModelWindowCompareItem(BaseModel):
    model_name: str
    purpose: str
    current_call_count: int
    baseline_call_count: int
    current_success_rate: float
    baseline_success_rate: float
    delta_success_rate: float
    current_avg_latency_ms: float
    baseline_avg_latency_ms: float
    delta_avg_latency_ms: float
    current_estimated_cost_usd: float
    baseline_estimated_cost_usd: float
    delta_estimated_cost_usd: float
    current_top_failure_type: str | None = None
    baseline_top_failure_type: str | None = None


class ExpertModelWindowCompareResponse(BaseModel):
    project_id: str | None = None
    days: int
    baseline_days: int
    items: list[ExpertModelWindowCompareItem]


class ExpertThresholdUpdateRequest(BaseModel):
    low_confidence: float | None = None
    strong_review_confidence: float | None = None
    max_section_pages: float | None = None
    max_chunk_tokens: float | None = None
    chunk_overlap_tokens: float | None = None


class ExpertThresholdResponse(BaseModel):
    values: dict[str, float]
    source: dict = Field(default_factory=dict)


class ExpertThresholdPublishRequest(BaseModel):
    actor_user_id: str | None = None
    reason: str | None = None


class ExpertThresholdRecommendationItem(BaseModel):
    key: str
    current_value: float
    suggested_value: float
    go_live_value: float
    reason: str


class ExpertThresholdRecommendationResponse(BaseModel):
    project_id: str | None = None
    industry_tag: str | None = None
    low_quality_rate: float
    kb_failed_count: int
    suggestions: list[ExpertThresholdRecommendationItem]


class ExpertDocTypeBreakdownItem(BaseModel):
    doc_type: str
    doc_count: int
    chunk_count: int
    avg_quality_score: float
    low_quality_chunk_count: int
    low_quality_rate: float


class ExpertIngestStepBreakdownItem(BaseModel):
    step: str
    run_count: int
    ratio: float


class ExpertQualityDetailResponse(BaseModel):
    project_id: str | None = None
    industry_tag: str | None = None
    days: int
    by_doc_type: list[ExpertDocTypeBreakdownItem]
    by_ingest_step: list[ExpertIngestStepBreakdownItem]
    by_model: list[ExpertModelCompareItem]


def _parse_project_uuid(project_id: str | None) -> uuid.UUID | None:
    token = str(project_id or "").strip()
    if not token:
        return None
    try:
        return uuid.UUID(token)
    except ValueError as exc:
        raise ValueError("invalid project_id uuid") from exc


def _apply_expert_scope(
    stmt,
    *,
    project_uuid: uuid.UUID | None,
    industry_tag: str | None,
):
    if project_uuid:
        stmt = stmt.join(Document, ExpertDoc.source_document_id == Document.id).where(Document.project_id == project_uuid)
    if industry_tag:
        stmt = stmt.where(ExpertDoc.industry_tag == industry_tag)
    return stmt


def _query_model_compare(
    *,
    db: Session,
    project_uuid: uuid.UUID | None,
    days: int,
    limit: int,
) -> list[ExpertModelCompareItem]:
    bounded_days = max(1, min(int(days), 365))
    bounded_limit = max(1, min(int(limit), 200))
    since = datetime.now(UTC) - timedelta(days=bounded_days)

    stmt = (
        select(
            LLMCallLog.model_name,
            LLMCallLog.purpose,
            func.count(LLMCallLog.id),
            func.sum(case((LLMCallLog.blocked_reason.is_(None), 1), else_=0)),
            func.sum(case((LLMCallLog.fallback_count > 0, 1), else_=0)),
            func.sum(case((LLMCallLog.cache_hit.is_(True), 1), else_=0)),
            func.avg(LLMCallLog.latency_ms),
            func.avg(LLMCallLog.input_tokens),
            func.avg(LLMCallLog.output_tokens),
            func.sum(LLMCallLog.input_tokens),
            func.sum(LLMCallLog.output_tokens),
        )
        .where(LLMCallLog.created_at >= since)
        .group_by(LLMCallLog.model_name, LLMCallLog.purpose)
        .order_by(func.count(LLMCallLog.id).desc())
        .limit(bounded_limit)
    )
    if project_uuid:
        stmt = stmt.where(LLMCallLog.project_id == project_uuid)

    failure_stmt = (
        select(
            LLMCallLog.model_name,
            LLMCallLog.purpose,
            LLMCallLog.blocked_reason,
            func.count(LLMCallLog.id),
        )
        .where(LLMCallLog.created_at >= since, LLMCallLog.blocked_reason.is_not(None))
        .group_by(LLMCallLog.model_name, LLMCallLog.purpose, LLMCallLog.blocked_reason)
        .order_by(func.count(LLMCallLog.id).desc())
    )
    if project_uuid:
        failure_stmt = failure_stmt.where(LLMCallLog.project_id == project_uuid)
    failure_rows = db.execute(failure_stmt).all()
    top_failure_by_key: dict[tuple[str, str], tuple[str, int]] = {}
    for row in failure_rows:
        key = (str(row[0] or ""), str(row[1] or ""))
        reason = str(row[2] or "UNKNOWN")
        count = int(row[3] or 0)
        existing = top_failure_by_key.get(key)
        if existing is None or count > existing[1]:
            top_failure_by_key[key] = (reason, count)

    rows = db.execute(stmt).all()
    items: list[ExpertModelCompareItem] = []
    for row in rows:
        call_count = int(row[2] or 0)
        success_count = int(row[3] or 0)
        fallback_count = int(row[4] or 0)
        cache_hits = int(row[5] or 0)
        avg_input = float(row[7] or 0.0)
        avg_output = float(row[8] or 0.0)
        sum_input = float(row[9] or (avg_input * call_count if call_count else 0.0)) if len(row) > 9 else avg_input * call_count
        sum_output = (
            float(row[10] or (avg_output * call_count if call_count else 0.0)) if len(row) > 10 else avg_output * call_count
        )
        estimated_cost_usd = _estimate_cost_usd(model_name=str(row[0] or ""), input_tokens=int(sum_input), output_tokens=int(sum_output))
        failure_count = max(call_count - success_count, 0)
        failure_key = (str(row[0] or ""), str(row[1] or ""))
        top_failure_type = top_failure_by_key.get(failure_key, (None, 0))[0]
        if not top_failure_type and failure_count > 0 and fallback_count > 0:
            top_failure_type = "FALLBACK_OR_UNKNOWN"
        items.append(
            ExpertModelCompareItem(
                model_name=str(row[0] or ""),
                purpose=str(row[1] or ""),
                call_count=call_count,
                success_rate=round((success_count / call_count) if call_count else 0.0, 4),
                fallback_rate=round((fallback_count / call_count) if call_count else 0.0, 4),
                cache_hit_rate=round((cache_hits / call_count) if call_count else 0.0, 4),
                avg_latency_ms=round(float(row[6] or 0.0), 2),
                avg_input_tokens=round(avg_input, 2),
                avg_output_tokens=round(avg_output, 2),
                avg_total_tokens=round(avg_input + avg_output, 2),
                estimated_cost_usd=round(estimated_cost_usd, 6),
                failure_count=failure_count,
                top_failure_type=top_failure_type,
            )
        )
    return items


def _estimate_cost_usd(*, model_name: str, input_tokens: int, output_tokens: int) -> float:
    cost, currency = get_estimated_cost(model_name, input_tokens, output_tokens)
    if currency == "USD":
        return float(cost)
    if currency == "CNY":
        return float(cost) / 7.2
    return 0.0


def _extract_quality_signal_metrics(metadata_payload: object) -> dict[str, float | bool]:
    payload = metadata_payload if isinstance(metadata_payload, dict) else {}
    signals = payload.get("quality_signals") if isinstance(payload, dict) else {}
    if not isinstance(signals, dict):
        signals = {}
    key_field_completeness = signals.get("key_field_completeness")
    if key_field_completeness is None and isinstance(payload, dict):
        fields = (
            payload.get("voltage_level_kv"),
            payload.get("project_type"),
            payload.get("region"),
        )
        filled = sum(1 for item in fields if item not in (None, "", []))
        equipment = payload.get("core_equipment")
        if isinstance(equipment, list) and equipment:
            filled += 1
        key_field_completeness = filled / 4.0
    return {
        "schema_passed": bool(signals.get("schema_passed", False)),
        "key_field_completeness": _clamp(float(key_field_completeness or 0.0), 0.0, 1.0),
        "fallback_triggered": bool(signals.get("fallback_triggered", False)),
        "manual_review_required": bool(signals.get("manual_review_required", False)),
        "evidence_coverage": _clamp(float(signals.get("evidence_coverage", 0.0) or 0.0), 0.0, 1.0),
    }


def _build_model_window_compare(
    *,
    current_items: list[ExpertModelCompareItem],
    baseline_items: list[ExpertModelCompareItem],
    limit: int,
) -> list[ExpertModelWindowCompareItem]:
    by_key_current = {(item.model_name, item.purpose): item for item in current_items}
    by_key_baseline = {(item.model_name, item.purpose): item for item in baseline_items}
    keys = set(by_key_current.keys()) | set(by_key_baseline.keys())
    rows: list[ExpertModelWindowCompareItem] = []
    for key in keys:
        cur = by_key_current.get(key)
        base = by_key_baseline.get(key)
        rows.append(
            ExpertModelWindowCompareItem(
                model_name=key[0],
                purpose=key[1],
                current_call_count=int(cur.call_count if cur else 0),
                baseline_call_count=int(base.call_count if base else 0),
                current_success_rate=float(cur.success_rate if cur else 0.0),
                baseline_success_rate=float(base.success_rate if base else 0.0),
                delta_success_rate=round(float((cur.success_rate if cur else 0.0) - (base.success_rate if base else 0.0)), 4),
                current_avg_latency_ms=float(cur.avg_latency_ms if cur else 0.0),
                baseline_avg_latency_ms=float(base.avg_latency_ms if base else 0.0),
                delta_avg_latency_ms=round(float((cur.avg_latency_ms if cur else 0.0) - (base.avg_latency_ms if base else 0.0)), 2),
                current_estimated_cost_usd=float(cur.estimated_cost_usd if cur else 0.0),
                baseline_estimated_cost_usd=float(base.estimated_cost_usd if base else 0.0),
                delta_estimated_cost_usd=round(
                    float((cur.estimated_cost_usd if cur else 0.0) - (base.estimated_cost_usd if base else 0.0)),
                    6,
                ),
                current_top_failure_type=cur.top_failure_type if cur else None,
                baseline_top_failure_type=base.top_failure_type if base else None,
            )
        )
    rows.sort(key=lambda item: (item.current_call_count, item.baseline_call_count), reverse=True)
    return rows[: max(1, min(limit, 200))]


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _to_float(values: dict[str, float], key: str, default: float) -> float:
    raw = values.get(key, default)
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _build_threshold_diff(before: dict[str, float], after: dict[str, float]) -> dict[str, dict[str, float]]:
    keys = set(before.keys()) | set(after.keys())
    changed: dict[str, dict[str, float]] = {}
    for key in keys:
        old_v = _to_float(before, key, 0.0)
        new_v = _to_float(after, key, 0.0)
        if round(old_v, 6) == round(new_v, 6):
            continue
        changed[key] = {"from": round(old_v, 6), "to": round(new_v, 6)}
    return changed


def _build_threshold_recommendations(
    *,
    current_values: dict[str, float],
    go_live_values: dict[str, float],
    quality: ExpertQualityStats,
) -> list[ExpertThresholdRecommendationItem]:
    low_confidence = _to_float(current_values, "low_confidence", 0.6)
    strong_review = _to_float(current_values, "strong_review_confidence", 0.75)
    max_section_pages = _to_float(current_values, "max_section_pages", 20.0)
    max_chunk_tokens = _to_float(current_values, "max_chunk_tokens", 1200.0)
    chunk_overlap_tokens = _to_float(current_values, "chunk_overlap_tokens", 100.0)

    low_quality_rate = float(quality.low_quality_rate or 0.0)
    kb_failed_count = int(quality.kb_failed_count or 0)
    avg_quality_score = float(quality.avg_quality_score or 0.0)

    low_confidence_suggested = low_confidence
    low_confidence_reason = "低质量率在稳定区间，保持当前阈值。"
    if low_quality_rate >= 0.15:
        low_confidence_suggested = _clamp(low_confidence + 0.05, 0.40, 0.90)
        low_confidence_reason = "低质量率偏高，提升 low_confidence 加强低分切片识别。"
    elif low_quality_rate <= 0.05 and kb_failed_count == 0:
        low_confidence_suggested = _clamp(low_confidence - 0.03, 0.40, 0.90)
        low_confidence_reason = "低质量率较低且无失败，可适度下调阈值减少误报。"

    strong_review_suggested = strong_review
    strong_review_reason = "复核阈值稳定，暂不调整。"
    if kb_failed_count > 0 or low_quality_rate >= 0.12:
        strong_review_suggested = _clamp(strong_review + 0.03, 0.60, 0.95)
        strong_review_reason = "存在失败或低质量偏高，提升强制复核阈值。"
    elif low_quality_rate <= 0.05 and kb_failed_count == 0:
        strong_review_suggested = _clamp(strong_review - 0.02, 0.60, 0.95)
        strong_review_reason = "整体质量稳定，可下调复核阈值以减少人工负担。"

    max_section_pages_suggested = max_section_pages
    max_section_pages_reason = "章节页数阈值保持不变。"
    if kb_failed_count > 0:
        max_section_pages_suggested = max(8.0, max_section_pages - 2.0)
        max_section_pages_reason = "出现失败记录，收紧单章节页数上限降低解析风险。"

    max_chunk_tokens_suggested = max_chunk_tokens
    max_chunk_tokens_reason = "切片长度阈值保持不变。"
    if avg_quality_score < 80 and low_quality_rate >= 0.10:
        max_chunk_tokens_suggested = max(400.0, round(max_chunk_tokens * 0.9, 0))
        max_chunk_tokens_reason = "平均质量偏低，缩短切片长度提升抽取稳定性。"
    elif avg_quality_score >= 90 and low_quality_rate <= 0.03:
        max_chunk_tokens_suggested = min(4000.0, round(max_chunk_tokens * 1.1, 0))
        max_chunk_tokens_reason = "质量稳定，可适度增大切片长度减少碎片化。"

    chunk_overlap_tokens_suggested = chunk_overlap_tokens
    chunk_overlap_tokens_reason = "重叠阈值保持不变。"
    if low_quality_rate >= 0.10:
        chunk_overlap_tokens_suggested = min(
            round(max_chunk_tokens_suggested * 0.5, 0),
            max(chunk_overlap_tokens, round(chunk_overlap_tokens + 20.0, 0)),
        )
        chunk_overlap_tokens_reason = "低质量率偏高，增加重叠以降低切片断裂带来的信息丢失。"

    rows = [
        (
            "low_confidence",
            low_confidence,
            low_confidence_suggested,
            low_confidence_reason,
        ),
        (
            "strong_review_confidence",
            strong_review,
            strong_review_suggested,
            strong_review_reason,
        ),
        (
            "max_section_pages",
            max_section_pages,
            max_section_pages_suggested,
            max_section_pages_reason,
        ),
        (
            "max_chunk_tokens",
            max_chunk_tokens,
            max_chunk_tokens_suggested,
            max_chunk_tokens_reason,
        ),
        (
            "chunk_overlap_tokens",
            chunk_overlap_tokens,
            chunk_overlap_tokens_suggested,
            chunk_overlap_tokens_reason,
        ),
    ]

    suggestions: list[ExpertThresholdRecommendationItem] = []
    for key, current, suggested, reason in rows:
        current_v = round(float(current), 4)
        suggested_v = round(float(suggested), 4)
        go_live_v = round(_to_float(go_live_values, key, current_v), 4)
        suggestions.append(
            ExpertThresholdRecommendationItem(
                key=key,
                current_value=current_v,
                suggested_value=suggested_v,
                go_live_value=go_live_v,
                reason=reason,
            )
        )
    return suggestions


@router.get("/usage", response_model=UsageStatsResponse)
def get_usage_stats(db: Session = Depends(get_db)):
    """
    Get aggregated token usage and estimated cost by model.
    """
    # Group by model_name
    stmt = (
        select(
            LLMCallLog.model_name,
            func.sum(LLMCallLog.input_tokens).label("input_sum"),
            func.sum(LLMCallLog.output_tokens).label("output_sum"),
            func.count(LLMCallLog.id).label("call_count"),
        )
        .group_by(LLMCallLog.model_name)
    )

    rows = db.execute(stmt).all()

    items: list[ModelUsageStats] = []
    total_usd = 0.0

    for row in rows:
        model_name = row.model_name
        input_tokens = int(row.input_sum or 0)
        output_tokens = int(row.output_sum or 0)
        call_count = int(row.call_count or 0)

        cost, currency = get_estimated_cost(model_name, input_tokens, output_tokens)

        # Simple normalization for total aggregation (assuming roughly 1 USD for all for simplicity in header)
        # In a real app, might need currency conversion. Here we just sum up.
        if currency == "USD":
            total_usd += cost
        elif currency == "CNY":  # If we added CNY support
            total_usd += cost / 7.2  # Approx exchange rate

        items.append(
            ModelUsageStats(
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                call_count=call_count,
                estimated_cost=round(cost, 4),
                currency=currency,
            )
        )

    return UsageStatsResponse(items=items, total_cost_usd=round(total_usd, 4))


@router.get("/expert-quality", response_model=ExpertQualityStatsResponse)
def get_expert_quality_stats(
    project_id: str | None = None,
    industry_tag: str | None = None,
    db: Session = Depends(get_db),
):
    try:
        project_uuid = _parse_project_uuid(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    threshold_payload = get_expert_library_thresholds()
    thresholds = threshold_payload.get("values", {}) if isinstance(threshold_payload, dict) else {}
    low_threshold = float(thresholds.get("low_confidence", 0.6)) * 100.0

    doc_stmt = select(func.count(func.distinct(ExpertDoc.id))).select_from(ExpertDoc)
    doc_stmt = _apply_expert_scope(doc_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    doc_count = int(db.execute(doc_stmt).scalar() or 0)

    chunk_stmt = (
        select(func.count(EvidenceChunk.id), func.avg(EvidenceChunk.quality_score))
        .select_from(EvidenceChunk)
        .join(ExpertDoc, EvidenceChunk.expert_doc_id == ExpertDoc.id)
    )
    chunk_stmt = _apply_expert_scope(chunk_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    chunk_row = db.execute(chunk_stmt).one()
    chunk_count = int(chunk_row[0] or 0)
    avg_quality = round(float(chunk_row[1] or 0.0), 2)

    low_stmt = (
        select(func.count(EvidenceChunk.id))
        .select_from(EvidenceChunk)
        .join(ExpertDoc, EvidenceChunk.expert_doc_id == ExpertDoc.id)
        .where(EvidenceChunk.quality_score < low_threshold)
    )
    low_stmt = _apply_expert_scope(low_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    low_quality_count = int(db.execute(low_stmt).scalar() or 0)
    low_quality_rate = round((low_quality_count / chunk_count) if chunk_count else 0.0, 4)

    pricing_stmt = (
        select(EvidenceChunk.forbidden_tags)
        .select_from(EvidenceChunk)
        .join(ExpertDoc, EvidenceChunk.expert_doc_id == ExpertDoc.id)
    )
    pricing_stmt = _apply_expert_scope(pricing_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    pricing_related_count = 0
    for (tags,) in db.execute(pricing_stmt):
        if isinstance(tags, list) and "PRICING_RELATED" in {str(item) for item in tags}:
            pricing_related_count += 1

    kb_stmt = (
        select(KBIngestRun.current_step, func.count(KBIngestRun.id))
        .select_from(KBIngestRun)
        .join(ExpertDoc, KBIngestRun.expert_doc_id == ExpertDoc.id)
        .group_by(KBIngestRun.current_step)
    )
    kb_stmt = _apply_expert_scope(kb_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    kb_rows = db.execute(kb_stmt).all()
    kb_ready_count = 0
    kb_failed_count = 0
    for step, count in kb_rows:
        if step == KBIngestStep.KB_READY:
            kb_ready_count = int(count or 0)
        if step == KBIngestStep.FAILED:
            kb_failed_count = int(count or 0)

    metadata_stmt = (
        select(KBIngestRun.metadata_json)
        .select_from(KBIngestRun)
        .join(ExpertDoc, KBIngestRun.expert_doc_id == ExpertDoc.id)
    )
    metadata_stmt = _apply_expert_scope(metadata_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    signal_rows = db.execute(metadata_stmt)
    run_count = 0
    schema_pass_count = 0
    fallback_trigger_count = 0
    manual_review_count = 0
    key_field_sum = 0.0
    evidence_coverage_sum = 0.0
    for (metadata_payload,) in signal_rows:
        run_count += 1
        metrics = _extract_quality_signal_metrics(metadata_payload)
        if metrics["schema_passed"]:
            schema_pass_count += 1
        if metrics["fallback_triggered"]:
            fallback_trigger_count += 1
        if metrics["manual_review_required"]:
            manual_review_count += 1
        key_field_sum += float(metrics["key_field_completeness"])
        evidence_coverage_sum += float(metrics["evidence_coverage"])

    schema_pass_rate = round((schema_pass_count / run_count) if run_count else 0.0, 4)
    key_field_completeness_rate = round((key_field_sum / run_count) if run_count else 0.0, 4)
    fallback_trigger_rate = round((fallback_trigger_count / run_count) if run_count else 0.0, 4)
    manual_review_rate = round((manual_review_count / run_count) if run_count else 0.0, 4)
    evidence_coverage_rate = round((evidence_coverage_sum / run_count) if run_count else 0.0, 4)

    return ExpertQualityStatsResponse(
        project_id=project_id,
        industry_tag=industry_tag,
        stats=ExpertQualityStats(
            doc_count=doc_count,
            chunk_count=chunk_count,
            avg_quality_score=avg_quality,
            low_quality_chunk_count=low_quality_count,
            low_quality_rate=low_quality_rate,
            pricing_related_chunk_count=pricing_related_count,
            kb_ready_count=kb_ready_count,
            kb_failed_count=kb_failed_count,
            low_quality_threshold=round(low_threshold, 2),
            schema_pass_rate=schema_pass_rate,
            key_field_completeness_rate=key_field_completeness_rate,
            fallback_trigger_rate=fallback_trigger_rate,
            manual_review_rate=manual_review_rate,
            evidence_coverage_rate=evidence_coverage_rate,
        ),
        thresholds=thresholds if isinstance(thresholds, dict) else {},
        threshold_source=threshold_payload.get("source", {}) if isinstance(threshold_payload, dict) else {},
    )


@router.get("/expert-model-compare", response_model=ExpertModelCompareResponse)
def get_expert_model_compare(
    project_id: str | None = None,
    days: int = 30,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    try:
        project_uuid = _parse_project_uuid(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    bounded_days = max(1, min(int(days), 365))
    bounded_limit = max(1, min(int(limit), 200))
    items = _query_model_compare(
        db=db,
        project_uuid=project_uuid,
        days=bounded_days,
        limit=bounded_limit,
    )

    return ExpertModelCompareResponse(
        project_id=project_id,
        days=bounded_days,
        items=items,
    )


@router.get("/expert-model-compare-window", response_model=ExpertModelWindowCompareResponse)
def get_expert_model_compare_window(
    project_id: str | None = None,
    days: int = 30,
    baseline_days: int = 90,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    try:
        project_uuid = _parse_project_uuid(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    bounded_days = max(1, min(int(days), 365))
    bounded_baseline_days = max(1, min(int(baseline_days), 365))
    bounded_limit = max(1, min(int(limit), 200))
    current_items = _query_model_compare(
        db=db,
        project_uuid=project_uuid,
        days=bounded_days,
        limit=bounded_limit,
    )
    baseline_items = _query_model_compare(
        db=db,
        project_uuid=project_uuid,
        days=bounded_baseline_days,
        limit=bounded_limit,
    )
    merged_items = _build_model_window_compare(
        current_items=current_items,
        baseline_items=baseline_items,
        limit=bounded_limit,
    )
    return ExpertModelWindowCompareResponse(
        project_id=project_id,
        days=bounded_days,
        baseline_days=bounded_baseline_days,
        items=merged_items,
    )


@router.get("/expert-quality-detail", response_model=ExpertQualityDetailResponse)
def get_expert_quality_detail(
    project_id: str | None = None,
    industry_tag: str | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    try:
        project_uuid = _parse_project_uuid(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    bounded_days = max(1, min(int(days), 365))
    threshold_payload = get_expert_library_thresholds()
    thresholds = threshold_payload.get("values", {}) if isinstance(threshold_payload, dict) else {}
    low_threshold = float(thresholds.get("low_confidence", 0.6)) * 100.0

    doc_type_stmt = (
        select(
            ExpertDoc.doc_type,
            func.count(func.distinct(ExpertDoc.id)),
            func.count(EvidenceChunk.id),
            func.avg(EvidenceChunk.quality_score),
            func.sum(case((EvidenceChunk.quality_score < low_threshold, 1), else_=0)),
        )
        .select_from(ExpertDoc)
        .outerjoin(EvidenceChunk, EvidenceChunk.expert_doc_id == ExpertDoc.id)
        .group_by(ExpertDoc.doc_type)
        .order_by(func.count(EvidenceChunk.id).desc())
    )
    doc_type_stmt = _apply_expert_scope(doc_type_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    by_doc_type: list[ExpertDocTypeBreakdownItem] = []
    for row in db.execute(doc_type_stmt).all():
        doc_type = str(row[0] or "UNKNOWN")
        doc_count = int(row[1] or 0)
        chunk_count = int(row[2] or 0)
        avg_quality = round(float(row[3] or 0.0), 2)
        low_count = int(row[4] or 0)
        by_doc_type.append(
            ExpertDocTypeBreakdownItem(
                doc_type=doc_type,
                doc_count=doc_count,
                chunk_count=chunk_count,
                avg_quality_score=avg_quality,
                low_quality_chunk_count=low_count,
                low_quality_rate=round((low_count / chunk_count) if chunk_count else 0.0, 4),
            )
        )

    ingest_stmt = (
        select(KBIngestRun.current_step, func.count(KBIngestRun.id))
        .select_from(KBIngestRun)
        .join(ExpertDoc, KBIngestRun.expert_doc_id == ExpertDoc.id)
        .group_by(KBIngestRun.current_step)
        .order_by(func.count(KBIngestRun.id).desc())
    )
    ingest_stmt = _apply_expert_scope(ingest_stmt, project_uuid=project_uuid, industry_tag=industry_tag)
    ingest_rows = db.execute(ingest_stmt).all()
    total_runs = sum(int(row[1] or 0) for row in ingest_rows)
    by_ingest_step = [
        ExpertIngestStepBreakdownItem(
            step=str(row[0].value if hasattr(row[0], "value") else (row[0] if row[0] is not None else "UNKNOWN")),
            run_count=int(row[1] or 0),
            ratio=round((int(row[1] or 0) / total_runs) if total_runs else 0.0, 4),
        )
        for row in ingest_rows
    ]

    by_model = _query_model_compare(
        db=db,
        project_uuid=project_uuid,
        days=bounded_days,
        limit=200,
    )
    return ExpertQualityDetailResponse(
        project_id=project_id,
        industry_tag=industry_tag,
        days=bounded_days,
        by_doc_type=by_doc_type,
        by_ingest_step=by_ingest_step,
        by_model=by_model,
    )


@router.get("/expert-quality-export")
def export_expert_quality_csv(
    project_id: str | None = None,
    industry_tag: str | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
):
    summary = get_expert_quality_stats(project_id=project_id, industry_tag=industry_tag, db=db)
    detail = get_expert_quality_detail(project_id=project_id, industry_tag=industry_tag, days=days, db=db)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["dimension", "name", "metric", "value"])
    stats = summary.stats
    writer.writerow(["quality_control", "global", "schema_pass_rate", stats.schema_pass_rate])
    writer.writerow(["quality_control", "global", "key_field_completeness_rate", stats.key_field_completeness_rate])
    writer.writerow(["quality_control", "global", "fallback_trigger_rate", stats.fallback_trigger_rate])
    writer.writerow(["quality_control", "global", "manual_review_rate", stats.manual_review_rate])
    writer.writerow(["quality_control", "global", "evidence_coverage_rate", stats.evidence_coverage_rate])
    for item in detail.by_doc_type:
        writer.writerow(["doc_type", item.doc_type, "doc_count", item.doc_count])
        writer.writerow(["doc_type", item.doc_type, "chunk_count", item.chunk_count])
        writer.writerow(["doc_type", item.doc_type, "avg_quality_score", item.avg_quality_score])
        writer.writerow(["doc_type", item.doc_type, "low_quality_chunk_count", item.low_quality_chunk_count])
        writer.writerow(["doc_type", item.doc_type, "low_quality_rate", item.low_quality_rate])
    for item in detail.by_ingest_step:
        writer.writerow(["ingest_step", item.step, "run_count", item.run_count])
        writer.writerow(["ingest_step", item.step, "ratio", item.ratio])
    for item in detail.by_model:
        name = f"{item.model_name}|{item.purpose}"
        writer.writerow(["model", name, "call_count", item.call_count])
        writer.writerow(["model", name, "success_rate", item.success_rate])
        writer.writerow(["model", name, "fallback_rate", item.fallback_rate])
        writer.writerow(["model", name, "cache_hit_rate", item.cache_hit_rate])
        writer.writerow(["model", name, "avg_latency_ms", item.avg_latency_ms])
        writer.writerow(["model", name, "avg_total_tokens", item.avg_total_tokens])
        writer.writerow(["model", name, "estimated_cost_usd", item.estimated_cost_usd])
        writer.writerow(["model", name, "failure_count", item.failure_count])
        writer.writerow(["model", name, "top_failure_type", item.top_failure_type or ""])
    content = buffer.getvalue()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"expert_quality_detail_{stamp}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/expert-thresholds", response_model=ExpertThresholdResponse)
def get_expert_thresholds_stats() -> ExpertThresholdResponse:
    payload = get_expert_library_thresholds()
    values = payload.get("values", {}) if isinstance(payload, dict) else {}
    source = payload.get("source", {}) if isinstance(payload, dict) else {}
    return ExpertThresholdResponse(values=values, source=source)


@router.put("/expert-thresholds", response_model=ExpertThresholdResponse)
def put_expert_thresholds_stats(payload: ExpertThresholdUpdateRequest) -> ExpertThresholdResponse:
    patch = payload.model_dump(exclude_none=True)
    try:
        updated = update_expert_library_thresholds(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = updated.get("values", {}) if isinstance(updated, dict) else {}
    source = updated.get("source", {}) if isinstance(updated, dict) else {}
    return ExpertThresholdResponse(values=values, source=source)


@router.get("/expert-threshold-go-live", response_model=ExpertThresholdResponse)
def get_expert_go_live_thresholds_stats() -> ExpertThresholdResponse:
    payload = get_expert_library_go_live_thresholds()
    values = payload.get("values", {}) if isinstance(payload, dict) else {}
    source = payload.get("source", {}) if isinstance(payload, dict) else {}
    return ExpertThresholdResponse(values=values, source=source)


@router.put("/expert-threshold-go-live", response_model=ExpertThresholdResponse)
def put_expert_go_live_thresholds_stats(payload: ExpertThresholdUpdateRequest) -> ExpertThresholdResponse:
    patch = payload.model_dump(exclude_none=True)
    try:
        updated = update_expert_library_go_live_thresholds(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = updated.get("values", {}) if isinstance(updated, dict) else {}
    source = updated.get("source", {}) if isinstance(updated, dict) else {}
    return ExpertThresholdResponse(values=values, source=source)


@router.post("/expert-threshold-go-live/publish", response_model=ExpertThresholdResponse)
def post_expert_go_live_thresholds_publish(
    payload: ExpertThresholdPublishRequest | None = None,
    project_id: str | None = None,
    db: Session = Depends(get_db),
) -> ExpertThresholdResponse:
    try:
        project_uuid = _parse_project_uuid(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    before_payload = get_expert_library_thresholds()
    before_values = before_payload.get("values", {}) if isinstance(before_payload, dict) else {}
    go_live_payload = get_expert_library_go_live_thresholds()
    go_live_values = go_live_payload.get("values", {}) if isinstance(go_live_payload, dict) else {}
    try:
        updated = publish_expert_library_go_live_thresholds()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = updated.get("values", {}) if isinstance(updated, dict) else {}
    source = updated.get("source", {}) if isinstance(updated, dict) else {}
    changed = _build_threshold_diff(
        before=before_values if isinstance(before_values, dict) else {},
        after=values if isinstance(values, dict) else {},
    )
    actor_user_id = ((payload.actor_user_id if payload else None) or "system").strip() or "system"
    reason = (payload.reason if payload else None) or "manual_publish_go_live_thresholds"
    db.add(
        AuditLog(
            project_id=project_uuid,
            actor_user_id=actor_user_id,
            action="expert_threshold.go_live_publish",
            target_id=None,
            metadata_json={
                "reason": reason,
                "changed_fields": sorted(changed.keys()),
                "diff": changed,
                "runtime_values": values,
                "go_live_values": go_live_values,
                "published_at": datetime.now(UTC).isoformat(),
            },
        )
    )
    db.commit()
    return ExpertThresholdResponse(values=values, source=source)


@router.get("/expert-threshold-recommendation", response_model=ExpertThresholdRecommendationResponse)
def get_expert_threshold_recommendation(
    project_id: str | None = None,
    industry_tag: str | None = None,
    db: Session = Depends(get_db),
) -> ExpertThresholdRecommendationResponse:
    quality_response = get_expert_quality_stats(project_id=project_id, industry_tag=industry_tag, db=db)
    current_values = quality_response.thresholds if isinstance(quality_response.thresholds, dict) else {}
    go_live_payload = get_expert_library_go_live_thresholds()
    go_live_values = go_live_payload.get("values", {}) if isinstance(go_live_payload, dict) else {}
    suggestions = _build_threshold_recommendations(
        current_values=current_values,
        go_live_values=go_live_values,
        quality=quality_response.stats,
    )
    return ExpertThresholdRecommendationResponse(
        project_id=project_id,
        industry_tag=industry_tag,
        low_quality_rate=quality_response.stats.low_quality_rate,
        kb_failed_count=quality_response.stats.kb_failed_count,
        suggestions=suggestions,
    )
