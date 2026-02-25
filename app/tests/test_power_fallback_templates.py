"""Power engineering fallback template tests."""
from __future__ import annotations

from app.services.fallback_templates import _SECTION_TEMPLATES, render_fallback_template


POWER_TEMPLATE_TYPES = [
    "commissioning_plan",
    "stringing_plan",
    "equipment_installation_plan",
    "grounding_plan",
    "cable_laying_plan",
]


def test_all_5_power_templates_exist():
    for ttype in POWER_TEMPLATE_TYPES:
        assert ttype in _SECTION_TEMPLATES, f"Missing template: {ttype}"


def test_commissioning_plan_references_standards():
    template = _SECTION_TEMPLATES["commissioning_plan"]
    assert "DL/T 5218" in template
    assert "GB 50150" in template


def test_grounding_plan_references_standard():
    template = _SECTION_TEMPLATES["grounding_plan"]
    assert "DL/T 621" in template


def test_cable_laying_plan_references_standard():
    template = _SECTION_TEMPLATES["cable_laying_plan"]
    assert "GB 50217" in template


def test_construction_plan_deepened_with_power_standards():
    template = _SECTION_TEMPLATES["construction_plan"]
    assert "GB 50233" in template
    assert "DL/T 5161" in template


def test_render_commissioning_plan():
    result = render_fallback_template(
        section_type="commissioning_plan",
        requirement_text="调试变压器",
        project_name="110kV变电站",
    )
    assert "调试方案" in result
    assert "110kV变电站" in result
    assert "调试变压器" in result


def test_render_stringing_plan():
    result = render_fallback_template(
        section_type="stringing_plan",
        requirement_text="架线施工",
        project_name="220kV输电线路",
    )
    assert "架线施工方案" in result or "张力放线" in result


def test_render_grounding_with_evidence():
    result = render_fallback_template(
        section_type="grounding_plan",
        requirement_text="接地电阻不大于0.5Ω",
        project_name="某变电站",
        evidence_texts=["接地网采用铜覆钢材料"],
    )
    assert "接地工程方案" in result or "接地" in result
    assert "铜覆钢" in result
