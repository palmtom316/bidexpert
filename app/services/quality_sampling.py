from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import date

from app.core.config import settings
from app.schemas.contracts import EvidenceUpsertItem


def _clamp(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _stable_rank(chunk_id: str) -> int:
    digest = hashlib.sha1(chunk_id.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _risk_level(chunk: EvidenceUpsertItem, *, reference_date: date) -> tuple[str, str]:
    score = float(chunk.quality_score or 0.0)
    low_score_threshold = float(getattr(settings, "knowledge_quality_low_score_threshold", 70.0))

    if (chunk.valid_to or "").strip():
        try:
            if date.fromisoformat(chunk.valid_to) < reference_date:
                return "high", "expired"
        except ValueError:
            pass

    if score < low_score_threshold:
        return "high", "low_quality"
    if score < (low_score_threshold + 10.0):
        return "medium", "borderline_quality"
    return "low", "random_sampling"


@dataclass(frozen=True)
class SamplingRecord:
    chunk_id: str
    sampled: bool
    risk_level: str
    reason: str
    quality_score: float
    valid_to: str | None


@dataclass(frozen=True)
class SamplingReport:
    total_chunks: int
    sampled_count: int
    configured_ratio: float
    actual_ratio: float
    estimated_accuracy: float
    accuracy_threshold: float
    manual_review_required: bool
    records: list[SamplingRecord]


def evaluate_quality_sampling(
    chunks: list[EvidenceUpsertItem],
    *,
    sampling_ratio: float | None = None,
    accuracy_threshold: float | None = None,
    reference_date: date | None = None,
) -> SamplingReport:
    today = reference_date or date.today()
    configured_ratio = float(
        sampling_ratio
        if sampling_ratio is not None
        else getattr(settings, "knowledge_sampling_ratio", 0.1)
    )
    configured_ratio = _clamp(configured_ratio, minimum=0.0, maximum=1.0)
    threshold = float(
        accuracy_threshold
        if accuracy_threshold is not None
        else getattr(settings, "knowledge_sampling_accuracy_threshold", 0.85)
    )
    threshold = _clamp(threshold, minimum=0.0, maximum=1.0)

    total = len(chunks)
    if total == 0:
        return SamplingReport(
            total_chunks=0,
            sampled_count=0,
            configured_ratio=configured_ratio,
            actual_ratio=0.0,
            estimated_accuracy=1.0,
            accuracy_threshold=threshold,
            manual_review_required=False,
            records=[],
        )

    target = max(1, int(math.ceil(total * configured_ratio)))
    scored: list[tuple[int, EvidenceUpsertItem, str, str]] = []
    for chunk in chunks:
        level, reason = _risk_level(chunk, reference_date=today)
        scored.append((_stable_rank(chunk.chunk_id), chunk, level, reason))

    high_risk = [item for item in scored if item[2] == "high"]
    medium_risk = [item for item in scored if item[2] == "medium"]
    low_risk = [item for item in scored if item[2] == "low"]

    sampled_ids: set[str] = {chunk.chunk_id for _, chunk, _, _ in high_risk}
    ordered_pool = sorted(medium_risk + low_risk, key=lambda pair: pair[0])
    for _, chunk, _, _ in ordered_pool:
        if len(sampled_ids) >= target:
            break
        sampled_ids.add(chunk.chunk_id)

    records: list[SamplingRecord] = []
    sampled_high = 0
    sampled_medium = 0
    for _, chunk, level, reason in sorted(scored, key=lambda pair: pair[0]):
        sampled = chunk.chunk_id in sampled_ids
        if sampled and level == "high":
            sampled_high += 1
        if sampled and level == "medium":
            sampled_medium += 1
        records.append(
            SamplingRecord(
                chunk_id=chunk.chunk_id,
                sampled=sampled,
                risk_level=level,
                reason=reason if sampled else "not_selected",
                quality_score=float(chunk.quality_score or 0.0),
                valid_to=chunk.valid_to,
            )
        )

    sampled_count = len(sampled_ids)
    sampled_count = max(0, sampled_count)
    actual_ratio = sampled_count / total if total else 0.0

    if sampled_count:
        risk_penalty = (sampled_high * 0.6 + sampled_medium * 0.3) / sampled_count
        estimated_accuracy = _clamp(1.0 - risk_penalty, minimum=0.0, maximum=1.0)
    else:
        estimated_accuracy = 1.0
    manual_review_required = estimated_accuracy < threshold

    return SamplingReport(
        total_chunks=total,
        sampled_count=sampled_count,
        configured_ratio=round(configured_ratio, 4),
        actual_ratio=round(actual_ratio, 4),
        estimated_accuracy=round(estimated_accuracy, 4),
        accuracy_threshold=round(threshold, 4),
        manual_review_required=manual_review_required,
        records=records,
    )
