from __future__ import annotations

from app.schemas.contracts import (
    ScoringV2Deduction,
    ScoringV2ItemResult,
    ScoringV2Request,
    ScoringV2Response,
)


def run_scoring_v2(payload: ScoringV2Request) -> ScoringV2Response:
    item_results: list[ScoringV2ItemResult] = []
    all_deductions: list[ScoringV2Deduction] = []
    evidence_map: dict[str, dict[str, list[str]]] = {}
    score_total = 0.0

    for item in payload.items:
        item_score = 0.0
        item_deductions: list[ScoringV2Deduction] = []
        item_evidence: dict[str, list[str]] = {}

        for point in item.points:
            item_evidence[point.point_id] = list(point.evidence_refs)
            weight = max(float(point.weight), 0.0)
            if point.negative_deviation:
                item_deductions.append(
                    ScoringV2Deduction(
                        item_id=item.item_id,
                        point_id=point.point_id,
                        reason="negative_deviation",
                        deducted_score=weight,
                    )
                )
                continue
            if point.arithmetic_conflict:
                item_deductions.append(
                    ScoringV2Deduction(
                        item_id=item.item_id,
                        point_id=point.point_id,
                        reason="arithmetic_conflict",
                        deducted_score=weight,
                    )
                )
                continue

            raw = (
                0.55 * float(point.cov)
                + 0.25 * float(point.evi)
                + 0.20 * float(point.spec)
                - 0.50 * float(point.risk)
            )
            normalized = _clamp(raw, 0.0, 1.0)
            point_score = weight * normalized
            item_score += point_score

            if normalized <= 0.0 and weight > 0:
                item_deductions.append(
                    ScoringV2Deduction(
                        item_id=item.item_id,
                        point_id=point.point_id,
                        reason="normalized_clamped_to_zero",
                        deducted_score=weight,
                    )
                )

        if item_score > float(item.max_score):
            deducted = item_score - float(item.max_score)
            item_deductions.append(
                ScoringV2Deduction(
                    item_id=item.item_id,
                    point_id="__item__",
                    reason="max_score_clamp",
                    deducted_score=deducted,
                )
            )
            item_score = float(item.max_score)

        score_total += item_score
        all_deductions.extend(item_deductions)
        evidence_map[item.item_id] = item_evidence
        item_results.append(
            ScoringV2ItemResult(
                item_id=item.item_id,
                score=round(item_score, 6),
                deductions=item_deductions,
                evidence_map=item_evidence,
            )
        )

    return ScoringV2Response(
        score_total=round(score_total, 6),
        items=item_results,
        deductions=all_deductions,
        evidence_map=evidence_map,
    )


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))
