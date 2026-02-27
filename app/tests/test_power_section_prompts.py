"""Power engineering section prompts, review checklists, and router keyword tests."""
from __future__ import annotations

from app.llm.prompt_suite_v11 import (
    _SECTION_GENERATION_GUIDANCE,
    _REVIEW_CHECKLIST,
    build_section_generation_prompt,
    build_review_prompt,
)
from app.core.section_router import (
    _DEFAULT_CRITICAL_KEYWORDS,
    is_critical_section,
)


POWER_SECTION_TYPES = [
    "commissioning_plan",
    "live_work_plan",
    "heavy_equipment_plan",
    "cable_laying_plan",
    "gis_installation_plan",
    "stringing_plan",
    "tower_foundation_plan",
    "grounding_plan",
    "anti_pollution_plan",
]


def test_all_9_power_section_types_in_guidance():
    for section_type in POWER_SECTION_TYPES:
        assert section_type in _SECTION_GENERATION_GUIDANCE, f"Missing guidance: {section_type}"


def test_all_9_power_section_types_in_review_checklist():
    for section_type in POWER_SECTION_TYPES:
        assert section_type in _REVIEW_CHECKLIST, f"Missing checklist: {section_type}"


def test_existing_checklists_enhanced_with_power_points():
    assert "电压等级" in _REVIEW_CHECKLIST["construction_plan"]
    assert "电力设备参数" in _REVIEW_CHECKLIST["technical_proposal"]
    assert "带电作业" in _REVIEW_CHECKLIST["safety_plan"]
    assert "电气试验" in _REVIEW_CHECKLIST["quality_plan"]


def test_commissioning_plan_references_standards():
    guidance = _SECTION_GENERATION_GUIDANCE["commissioning_plan"]
    assert "DL/T 5218" in guidance or "GB 50150" in guidance


def test_grounding_plan_references_standard():
    guidance = _SECTION_GENERATION_GUIDANCE["grounding_plan"]
    assert "DL/T 621" in guidance


def test_section_generation_prompt_includes_guidance():
    prompt = build_section_generation_prompt(
        global_facts_json={"project_name": "test"},
        relevant_requirements=["测试要求"],
        relevant_scoring=[],
        top_chunks=[],
        section_type="commissioning_plan",
    )
    assert "调试方案" in prompt


def test_review_prompt_includes_checklist():
    prompt = build_review_prompt(
        {"section_path": "test", "content": "测试内容"},
        section_type="commissioning_plan",
    )
    assert "调试程序" in prompt or "调试标准" in prompt


def test_power_keywords_in_default_critical():
    power_keywords = ["调试方案", "带电作业", "GIS安装", "继电保护", "变电站"]
    for kw in power_keywords:
        assert kw in _DEFAULT_CRITICAL_KEYWORDS, f"Missing keyword: {kw}"


def test_power_section_detected_as_critical():
    section = {"title": "110kV变电站GIS安装方案"}
    assert is_critical_section(section)
