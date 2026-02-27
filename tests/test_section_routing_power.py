"""Tests for power engineering section type detection and routing.

TDD RED phase — verifies that section titles are correctly mapped
to section_type keys used by prompt_suite and token limits.
"""

from __future__ import annotations


from app.core.section_router import (
    infer_section_type,
    is_critical_section,
)


class TestInferSectionType:
    """Test automatic section_type inference from section titles."""

    def test_construction_plan(self):
        assert infer_section_type("施工组织设计") == "construction_plan"

    def test_safety_plan(self):
        assert infer_section_type("安全施工方案") == "safety_plan"

    def test_quality_plan(self):
        assert infer_section_type("质量保证体系") == "quality_plan"

    def test_schedule_plan(self):
        assert infer_section_type("施工进度计划") == "schedule_plan"

    def test_environmental_plan(self):
        assert infer_section_type("环境保护方案") == "environmental_plan"

    def test_technical_proposal(self):
        assert infer_section_type("技术方案") == "technical_proposal"

    def test_commissioning_plan(self):
        assert infer_section_type("调试方案") == "commissioning_plan"

    def test_live_work_plan(self):
        assert infer_section_type("带电作业方案") == "live_work_plan"

    def test_cable_laying_plan(self):
        assert infer_section_type("电缆敷设方案") == "cable_laying_plan"

    def test_gis_installation_plan(self):
        assert infer_section_type("GIS安装方案") == "gis_installation_plan"

    def test_stringing_plan(self):
        assert infer_section_type("架线施工方案") == "stringing_plan"

    def test_tower_foundation_plan(self):
        assert infer_section_type("铁塔基础施工方案") == "tower_foundation_plan"

    def test_grounding_plan(self):
        assert infer_section_type("接地工程方案") == "grounding_plan"

    def test_anti_pollution_plan(self):
        assert infer_section_type("防污闪方案") == "anti_pollution_plan"

    def test_heavy_equipment_plan(self):
        assert infer_section_type("大型设备吊装运输方案") == "heavy_equipment_plan"

    def test_resource_plan(self):
        assert infer_section_type("资源配置方案") == "resource_plan"

    def test_commercial_proposal(self):
        assert infer_section_type("商务响应") == "commercial_proposal"

    def test_unknown_returns_none(self):
        assert infer_section_type("附件清单") is None

    def test_partial_match(self):
        # "第三章 施工组织设计" should still match
        assert infer_section_type("第三章 施工组织设计") == "construction_plan"

    def test_case_insensitive_gis(self):
        assert infer_section_type("gis安装方案") == "gis_installation_plan"


class TestPowerSectionCritical:
    """Verify power engineering sections are marked as critical."""

    def test_commissioning_is_critical(self):
        section = {"title": "调试方案"}
        assert is_critical_section(section) is True

    def test_live_work_is_critical(self):
        section = {"title": "带电作业方案"}
        assert is_critical_section(section) is True

    def test_gis_is_critical(self):
        section = {"title": "GIS安装方案"}
        assert is_critical_section(section) is True
