from __future__ import annotations

import json
from pathlib import Path

from app.extract.tender_parser import _parse_with_regex
from app.services.global_facts import detect_global_fact_conflicts, extract_global_facts_from_text


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_cases() -> list[dict]:
    cases: list[dict] = []
    for path in sorted(FIXTURE_DIR.glob("case_*.json")):
        cases.append(json.loads(path.read_text(encoding="utf-8")))
    return cases


def _evaluate_case(case: dict) -> tuple[float, float, float]:
    requirements = _parse_with_regex(case["tender_text"])

    disqual_expected = list(case.get("expected_disqualify_phrases", []))
    disqual_hit = sum(
        1
        for phrase in disqual_expected
        if any(
            phrase in item.original_text and bool(item.format_constraints.get("disqualify_rule"))
            for item in requirements
        )
    )
    disqual_score = disqual_hit / max(len(disqual_expected), 1)

    scoring_expected = list(case.get("expected_scoring_phrases", []))
    scoring_hit = sum(
        1
        for phrase in scoring_expected
        if any(
            phrase in item.original_text
            and (
                item.score_weight is not None
                or str(item.format_constraints.get("scoring_rule_type") or "").strip() in {"bonus", "penalty"}
            )
            for item in requirements
        )
    )
    scoring_score = scoring_hit / max(len(scoring_expected), 1)

    base_facts = extract_global_facts_from_text(case["base_facts_text"])
    candidate_facts = extract_global_facts_from_text(case["candidate_facts_text"])
    conflicts = detect_global_fact_conflicts(base_facts, candidate_facts)
    consistency_score = 1.0 if not conflicts else 0.0

    return disqual_score, scoring_score, consistency_score


def test_bid_quality_benchmark_thresholds() -> None:
    cases = _load_cases()
    assert len(cases) >= 10

    disqual_scores: list[float] = []
    scoring_scores: list[float] = []
    consistency_scores: list[float] = []
    for case in cases:
        disqual_score, scoring_score, consistency_score = _evaluate_case(case)
        disqual_scores.append(disqual_score)
        scoring_scores.append(scoring_score)
        consistency_scores.append(consistency_score)

    disqualify_coverage_rate = sum(disqual_scores) / len(disqual_scores)
    scoring_response_rate = sum(scoring_scores) / len(scoring_scores)
    key_param_consistency_rate = sum(consistency_scores) / len(consistency_scores)

    assert disqualify_coverage_rate == 1.0
    assert scoring_response_rate >= 0.95
    assert key_param_consistency_rate == 1.0
