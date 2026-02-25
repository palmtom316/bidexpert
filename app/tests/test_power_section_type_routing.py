"""Power section type routing detection tests."""
from __future__ import annotations

from app.core.section_router import (
    _POWER_SECTION_TYPE_MAP,
    detect_power_section_type,
)


def test_power_section_type_map_has_entries():
    assert len(_POWER_SECTION_TYPE_MAP) >= 10


def test_detect_substation():
    section = {"title": "110kV变电站安装方案"}
    assert detect_power_section_type(section) == "SUBSTATION"


def test_detect_transmission_line():
    section = {"title": "220kV输电线路施工方案"}
    assert detect_power_section_type(section) == "TRANSMISSION_LINE"


def test_detect_gis():
    section = {"title": "GIS设备安装调试方案"}
    assert detect_power_section_type(section) == "GIS_EQUIPMENT"


def test_detect_none_for_generic():
    section = {"title": "商务响应表"}
    assert detect_power_section_type(section) is None
