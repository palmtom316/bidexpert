from __future__ import annotations

import pytest

from app.schemas.contracts import ScoringV2ItemInput, ScoringV2PointInput, ScoringV2Request
from app.services.scoring_engine_v2 import run_scoring_v2


def test_score_formula_matches_v20_weights_and_clamp() -> None:
    payload = ScoringV2Request(
        project_id="proj-1",
        items=[
            ScoringV2ItemInput(
                item_id="I-1",
                max_score=10.0,
                points=[
                    ScoringV2PointInput(
                        point_id="P-1",
                        weight=10.0,
                        cov=0.8,
                        evi=0.6,
                        spec=0.5,
                        risk=0.2,
                        evidence_refs=["E-1"],
                    )
                ],
            )
        ],
    )
    result = run_scoring_v2(payload)

    # 0.55*0.8 + 0.25*0.6 + 0.20*0.5 - 0.50*0.2 = 0.59
    assert result.score_total == pytest.approx(5.9, rel=1e-6)
    assert result.items[0].score == pytest.approx(5.9, rel=1e-6)


def test_negative_deviation_or_arithmetic_conflict_forces_zero() -> None:
    payload = ScoringV2Request(
        project_id="proj-2",
        items=[
            ScoringV2ItemInput(
                item_id="I-2",
                max_score=20.0,
                points=[
                    ScoringV2PointInput(
                        point_id="P-neg",
                        weight=10.0,
                        cov=1.0,
                        evi=1.0,
                        spec=1.0,
                        risk=0.0,
                        negative_deviation=True,
                    ),
                    ScoringV2PointInput(
                        point_id="P-arith",
                        weight=10.0,
                        cov=1.0,
                        evi=1.0,
                        spec=1.0,
                        risk=0.0,
                        arithmetic_conflict=True,
                    ),
                ],
            )
        ],
    )
    result = run_scoring_v2(payload)

    assert result.score_total == 0.0
    assert any(d.reason == "negative_deviation" for d in result.deductions)
    assert any(d.reason == "arithmetic_conflict" for d in result.deductions)


def test_scoring_output_contains_deductions_and_evidence_map() -> None:
    payload = ScoringV2Request(
        project_id="proj-3",
        items=[
            ScoringV2ItemInput(
                item_id="I-3",
                max_score=10.0,
                points=[
                    ScoringV2PointInput(
                        point_id="P-3",
                        weight=10.0,
                        cov=0.1,
                        evi=0.1,
                        spec=0.1,
                        risk=0.8,
                        evidence_refs=["E-3-A", "E-3-B"],
                    )
                ],
            )
        ],
    )
    result = run_scoring_v2(payload)

    assert isinstance(result.deductions, list)
    assert "I-3" in result.evidence_map
    assert result.evidence_map["I-3"]["P-3"] == ["E-3-A", "E-3-B"]


def test_scoring_input_rejects_negative_weight_and_duplicate_ids() -> None:
    with pytest.raises(ValueError):
        ScoringV2PointInput(
            point_id="P-neg",
            weight=-1.0,
            cov=0.5,
            evi=0.5,
            spec=0.5,
            risk=0.5,
        )

    with pytest.raises(ValueError):
        ScoringV2Request(
            project_id="proj-x",
            items=[
                ScoringV2ItemInput(
                    item_id="I-dup",
                    max_score=10.0,
                    points=[
                        ScoringV2PointInput(point_id="P-1", weight=5, cov=0.5, evi=0.5, spec=0.5, risk=0.1),
                        ScoringV2PointInput(point_id="P-1", weight=5, cov=0.5, evi=0.5, spec=0.5, risk=0.1),
                    ],
                )
            ],
        )

    with pytest.raises(ValueError):
        ScoringV2Request(
            project_id="proj-y",
            items=[
                ScoringV2ItemInput(
                    item_id="I-1",
                    max_score=10.0,
                    points=[ScoringV2PointInput(point_id="P-1", weight=5, cov=0.5, evi=0.5, spec=0.5, risk=0.1)],
                ),
                ScoringV2ItemInput(
                    item_id="I-1",
                    max_score=10.0,
                    points=[ScoringV2PointInput(point_id="P-2", weight=5, cov=0.5, evi=0.5, spec=0.5, risk=0.1)],
                ),
            ],
        )
