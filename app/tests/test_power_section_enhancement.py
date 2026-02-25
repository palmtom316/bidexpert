"""Power engineering section enhancement tests (Tasks 14-15)."""
from __future__ import annotations

from app.services.section_enhancement import (
    _discipline,
    _electrical_section_subtype,
    enhance_section_metadata,
)


# Task 14: Expanded electrical keywords
def test_discipline_detects_relay_protection():
    assert _discipline("继电保护整定计算") == "ELECTRICAL"


def test_discipline_detects_gis():
    assert _discipline("GIS设备安装") == "ELECTRICAL"


def test_discipline_detects_transformer():
    assert _discipline("变压器安装调试") == "ELECTRICAL"


def test_discipline_detects_cable():
    assert _discipline("电缆敷设方案") == "ELECTRICAL"


def test_discipline_detects_grounding():
    assert _discipline("接地装置施工") == "ELECTRICAL"


def test_discipline_detects_kv():
    assert _discipline("110kV线路施工") == "ELECTRICAL"


def test_discipline_civil_unchanged():
    assert _discipline("土建基础施工") == "CIVIL"


def test_discipline_general_unchanged():
    assert _discipline("商务响应方案") == "GENERAL"


# Task 15: Finer electrical classification
def test_subtype_primary_system():
    assert _electrical_section_subtype("变压器安装方案") == "PRIMARY_SYSTEM"
    assert _electrical_section_subtype("GIS设备安装") == "PRIMARY_SYSTEM"


def test_subtype_secondary_system():
    assert _electrical_section_subtype("继电保护配置方案") == "SECONDARY_SYSTEM"
    assert _electrical_section_subtype("SCADA系统调试") == "SECONDARY_SYSTEM"


def test_subtype_civil_works():
    assert _electrical_section_subtype("变电站土建基础") == "CIVIL_WORKS"


def test_subtype_installation():
    assert _electrical_section_subtype("电缆敷设施工") == "ELECTRICAL_INSTALLATION"
    assert _electrical_section_subtype("铁塔组立方案") == "ELECTRICAL_INSTALLATION"


def test_subtype_commissioning():
    assert _electrical_section_subtype("交接试验方案") == "COMMISSIONING"
    assert _electrical_section_subtype("设备调试计划") == "COMMISSIONING"


def test_subtype_none_for_generic():
    assert _electrical_section_subtype("商务报价说明") is None


def test_enhance_metadata_includes_electrical_subtype():
    result = enhance_section_metadata("S-001", "GIS设备安装方案", "GIS设备安装与调试")
    assert result["discipline"] == "ELECTRICAL"
    assert result["electrical_subtype"] == "PRIMARY_SYSTEM"


def test_enhance_metadata_no_subtype_for_non_electrical():
    result = enhance_section_metadata("S-002", "商务响应", "商务条款逐项响应")
    assert result["electrical_subtype"] is None
