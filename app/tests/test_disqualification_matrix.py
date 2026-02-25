"""Disqualification matrix tests (Task 17)."""
from __future__ import annotations

from app.extract.tender_parser import ClauseStrength
from app.services.disqualification_matrix import (
    ConditionCategory,
    DisqualificationMatrix,
    DisqualificationResponse,
    build_matrix_from_requirements,
    check_section_against_matrix,
    _classify_category,
)


def test_build_matrix_extracts_conditions():
    reqs = ["投标人必须具备资质，未提供资质证书的将否决投标。报价超过最高限价的废标。"]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) >= 2
    ids = [c.condition_id for c in matrix.conditions]
    assert ids[0] == "DQ-001"


def test_build_matrix_deduplicates():
    reqs = [
        "未提供资质证书的将否决投标。",
        "未提供资质证书的将否决投标。",
    ]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) == 1


def test_build_matrix_strength_classification():
    reqs = ["废标条件：资质不符。", "资格审查不通过的不予受理。"]
    matrix = build_matrix_from_requirements(reqs)
    strengths = {c.strength for c in matrix.conditions}
    assert ClauseStrength.DISQUALIFY in strengths


def test_classify_category():
    assert _classify_category("未提供资质证书") == ConditionCategory.QUALIFICATION
    assert _classify_category("报价超过最高限价") == ConditionCategory.COMMERCIAL
    assert _classify_category("未按要求密封") == ConditionCategory.FORMAT
    assert _classify_category("安全方案缺失") == ConditionCategory.SAFETY
    assert _classify_category("技术偏离过大") == ConditionCategory.TECHNICAL


def test_coverage_rate_empty():
    matrix = DisqualificationMatrix(conditions=[], responses=[])
    assert matrix.coverage_rate() == 1.0


def test_coverage_rate_partial():
    reqs = ["否决投标条件一。废标条件二。"]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) >= 2
    # Mark first condition covered
    matrix.responses.append(
        DisqualificationResponse(condition_id=matrix.conditions[0].condition_id, covered=True)
    )
    rate = matrix.coverage_rate()
    assert 0.0 < rate < 1.0


def test_missing_conditions():
    reqs = ["否决投标。废标。"]
    matrix = build_matrix_from_requirements(reqs)
    missing = matrix.missing_conditions()
    assert len(missing) == len(matrix.conditions)  # none covered yet


def test_check_section_finds_coverage():
    reqs = ["未提供资质证书的将否决投标。"]
    matrix = build_matrix_from_requirements(reqs)
    section_text = "本公司已按要求提供资质证书，否决投标条款已满足。"
    updated = check_section_against_matrix(section_text, matrix)
    covered_ids = {r.condition_id for r in updated.responses if r.covered}
    assert len(covered_ids) >= 1


def test_check_section_reports_uncovered():
    reqs = ["未提供资质证书的将否决投标。"]
    matrix = build_matrix_from_requirements(reqs)
    section_text = "本方案采用先进施工工艺。"
    updated = check_section_against_matrix(section_text, matrix)
    missing = updated.missing_conditions()
    assert len(missing) >= 1


def test_disqualify_level_missing():
    reqs = ["废标条件：未按要求密封。资格审查不合格的不予通过。"]
    matrix = build_matrix_from_requirements(reqs)
    dl_missing = matrix.disqualify_level_missing()
    # The "废标" condition should be DISQUALIFY level and missing
    assert any(c.strength == ClauseStrength.DISQUALIFY for c in dl_missing)
