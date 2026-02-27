"""Pipeline disqualification gate tests (Task 18)."""
from __future__ import annotations

from app.services.disqualification_matrix import (
    build_matrix_from_requirements,
    check_section_against_matrix,
)
from app.extract.tender_parser import ClauseStrength


def test_pipeline_matrix_build_and_check_covered():
    """Simulates pre-gen build + post-gen check where section covers the condition."""
    reqs = ["未提供资质证书的将否决投标。"]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) >= 1

    section_text = "本单位已按招标要求提供完整资质证书，否决投标条款已响应。"
    updated = check_section_against_matrix(section_text, matrix)
    assert updated.coverage_rate() == 1.0
    assert len(updated.disqualify_level_missing()) == 0


def test_pipeline_matrix_uncovered_escalates():
    """Simulates post-gen check where DISQUALIFY condition is NOT addressed."""
    reqs = ["废标条件：未提供安全生产许可证。"]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) >= 1

    section_text = "本施工方案采用先进工艺，确保质量达标。"
    updated = check_section_against_matrix(section_text, matrix)
    fatal = updated.disqualify_level_missing()
    assert len(fatal) >= 1
    assert fatal[0].strength == ClauseStrength.DISQUALIFY


def test_pipeline_multiple_requirements():
    """Matrix built from multiple requirement texts."""
    reqs = [
        "资质不符的投标无效。",
        "未按要求密封的废标。",
        "报价超过最高限价的取消投标资格。",
    ]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) >= 3

    # Section addresses only one
    section_text = "本投标文件已按招标要求密封，废标条款已满足。"
    updated = check_section_against_matrix(section_text, matrix)
    assert updated.coverage_rate() < 1.0
    assert len(updated.missing_conditions()) >= 2


def test_pipeline_no_conditions_full_coverage():
    """Requirement with no disqualification terms produces empty matrix."""
    reqs = ["投标人应提供技术方案说明。"]
    matrix = build_matrix_from_requirements(reqs)
    assert len(matrix.conditions) == 0
    assert matrix.coverage_rate() == 1.0


def test_pipeline_soft_gate_never_blocks():
    """Verify the gate is soft — it only warns, matrix is always returnable."""
    reqs = ["废标条件：未提供资质。取消投标资格：围标串标。"]
    matrix = build_matrix_from_requirements(reqs)
    section_text = "无关内容。"
    updated = check_section_against_matrix(section_text, matrix)
    # Gate should produce warnings but never raise or block
    missing = updated.missing_conditions()
    assert len(missing) >= 1
    # coverage_rate always returns a float, never raises
    rate = updated.coverage_rate()
    assert isinstance(rate, float)
    assert 0.0 <= rate <= 1.0
