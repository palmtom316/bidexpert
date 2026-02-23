from __future__ import annotations

from app.services.generation_pipeline import _disqualify_coverage_ok, _global_fact_conflict_warnings


def test_generation_pipeline_flags_global_fact_conflicts() -> None:
    facts = {
        "project_name": "示例项目A",
        "total_duration_days": 120,
        "quality_standard": "合格",
    }
    generated_text = "项目名称: 示例项目B\n工期: 90天\n质量标准: 合格"

    warnings = _global_fact_conflict_warnings(facts, generated_text)

    assert "global_facts_conflict:project_name" in warnings
    assert "global_facts_conflict:total_duration_days" in warnings


def test_disqualify_coverage_gate_detects_missing_and_present_cases() -> None:
    assert _disqualify_coverage_ok(
        {"disqualify_clause_coverage": False, "issues": ["disqualify_missing"]},
        ["disqualify_missing"],
    ) is False

    assert _disqualify_coverage_ok(
        {"disqualify_clause_coverage": True, "issues": []},
        [],
    ) is True
