"""Tests for global facts extraction and pipeline integration.

TDD RED phase — defines expected behavior for extracting global facts
from tender documents and wiring them into the import pipeline.
"""

from __future__ import annotations

import json
import pytest

from app.tender.global_facts_extractor import extract_global_facts


class TestExtractGlobalFacts:
    """Test the global facts extraction from tender markdown text."""

    def test_extracts_project_name(self):
        text = "项目名称：某市110kV输变电工程施工项目"
        facts = extract_global_facts(text)
        assert facts["project_name"] is not None
        assert "110kV" in facts["project_name"] or "输变电" in facts["project_name"]

    def test_extracts_voltage_level(self):
        text = "本工程电压等级为110kV，新建110kV变电站一座。"
        facts = extract_global_facts(text)
        assert facts["voltage_level"] is not None
        assert "110" in str(facts["voltage_level"])

    def test_extracts_total_duration(self):
        text = "合同工期为365日历天，自开工令下达之日起算。"
        facts = extract_global_facts(text)
        assert facts["total_duration_days"] == 365

    def test_extracts_bid_bond(self):
        text = "投标保证金为人民币50万元整。"
        facts = extract_global_facts(text)
        assert facts["bid_bond_amount"] is not None

    def test_extracts_construction_unit(self):
        text = "建设单位：国网某省电力有限公司"
        facts = extract_global_facts(text)
        assert facts["construction_unit"] is not None

    def test_extracts_quality_standard(self):
        text = "质量标准：合格，争创优质工程。"
        facts = extract_global_facts(text)
        assert facts["quality_standard"] is not None

    def test_extracts_commissioning_deadline(self):
        text = "投运期限：2027年6月30日前完成送电投运。"
        facts = extract_global_facts(text)
        assert facts["commissioning_deadline"] is not None

    def test_extracts_tower_count(self):
        text = "新建铁塔68基，其中直线塔52基、耐张塔16基。"
        facts = extract_global_facts(text)
        assert facts["tower_count"] is not None

    def test_extracts_line_length(self):
        text = "线路全长约35.6公里，其中架空线路32.1公里，电缆线路3.5公里。"
        facts = extract_global_facts(text)
        assert facts["line_length"] is not None

    def test_extracts_substation_type(self):
        text = "新建户外式110kV变电站，主变容量2×50MVA。"
        facts = extract_global_facts(text)
        assert facts["substation_type"] is not None

    def test_returns_none_for_missing_fields(self):
        text = "这是一段普通文本，不包含任何工程信息。"
        facts = extract_global_facts(text)
        # Should return dict with all keys, missing values as None
        assert "project_name" in facts
        assert "voltage_level" in facts
        assert "tower_count" in facts

    def test_returns_all_28_fields(self):
        text = "项目名称：测试项目"
        facts = extract_global_facts(text)
        expected_keys = {
            "project_name", "project_location", "construction_unit",
            "supervision_unit", "design_unit", "total_duration_days",
            "project_manager", "voltage_level", "contract_amount",
            "quality_standard", "safety_level", "subcontract_restriction",
            "milestone_nodes", "bid_bond_amount", "performance_bond_ratio",
            "rated_capacity", "line_length", "conductor_type",
            "tower_count", "substation_type", "commissioning_deadline",
            "grid_connection_point", "seismic_fortification",
            "pollution_level", "altitude", "design_wind_speed",
            "annual_thunder_days", "owner_project_manager",
            "construction_permit_no", "epc_mode",
        }
        assert expected_keys.issubset(set(facts.keys()))

    def test_extracts_pollution_level(self):
        text = "本地区污秽等级为d级（重污区），外绝缘爬距按d级选取。"
        facts = extract_global_facts(text)
        assert facts["pollution_level"] is not None

    def test_extracts_seismic_fortification(self):
        text = "抗震设防烈度为7度，设计基本地震加速度值为0.10g。"
        facts = extract_global_facts(text)
        assert facts["seismic_fortification"] is not None
