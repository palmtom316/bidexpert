"""Power engineering GlobalFacts expansion tests."""
from __future__ import annotations

from app.services.global_facts import GlobalFacts, extract_global_facts_from_text, detect_global_fact_conflicts


def test_global_facts_has_rated_capacity_field():
    facts = GlobalFacts()
    assert hasattr(facts, "rated_capacity")


def test_global_facts_has_all_15_new_fields():
    new_fields = [
        "rated_capacity", "line_length", "conductor_type", "tower_count",
        "substation_type", "commissioning_deadline", "grid_connection_point",
        "seismic_fortification", "pollution_level", "altitude",
        "design_wind_speed", "annual_thunder_days", "owner_project_manager",
        "construction_permit_no", "epc_mode",
    ]
    for field in new_fields:
        assert field in GlobalFacts.model_fields, f"Missing field: {field}"


def test_extract_rated_capacity():
    text = "项目名称：某110kV变电站\n额定容量：50MVA"
    facts = extract_global_facts_from_text(text)
    assert facts["rated_capacity"] == "50MVA"


def test_extract_line_length():
    text = "项目名称：某输电线路\n线路长度：123.5km"
    facts = extract_global_facts_from_text(text)
    assert facts["line_length"] == "123.5km"


def test_extract_conductor_type():
    text = "项目名称：某线路\n导线型号：LGJ-400/50"
    facts = extract_global_facts_from_text(text)
    assert facts["conductor_type"] is not None
    assert "LGJ" in facts["conductor_type"]


def test_extract_tower_count():
    text = "项目名称：某线路\n杆塔数量：120基"
    facts = extract_global_facts_from_text(text)
    assert facts["tower_count"] == 120


def test_extract_pollution_level():
    text = "项目名称：某变电站\n污秽等级：d级"
    facts = extract_global_facts_from_text(text)
    assert facts["pollution_level"] is not None


def test_extract_annual_thunder_days():
    text = "项目名称：某线路\n年平均雷暴日：45天"
    facts = extract_global_facts_from_text(text)
    assert facts["annual_thunder_days"] == 45


def test_extract_altitude():
    text = "项目名称：某变电站\n海拔高度：1200m"
    facts = extract_global_facts_from_text(text)
    assert facts["altitude"] == "1200m"


def test_extract_design_wind_speed():
    text = "项目名称：某线路\n设计风速：27.5m/s"
    facts = extract_global_facts_from_text(text)
    assert facts["design_wind_speed"] == "27.5m/s"


def test_extract_compound_voltage():
    text = "项目名称：某变电站\n电压等级：220kV/110kV/35kV"
    facts = extract_global_facts_from_text(text)
    assert facts["voltage_level"] is not None
    assert "220" in facts["voltage_level"]


def test_extract_dc_voltage():
    text = "项目名称：某换流站\n电压等级：±800kV"
    facts = extract_global_facts_from_text(text)
    assert facts["voltage_level"] is not None


def test_conflict_detection_new_fields():
    base = {"rated_capacity": "50MVA", "tower_count": 120, "pollution_level": "d级"}
    candidate = {"rated_capacity": "63MVA", "tower_count": 120, "pollution_level": "d级"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert "rated_capacity" in conflicts
    assert "tower_count" not in conflicts


def test_extract_epc_mode():
    text = "项目名称：某变电站\n建设模式：EPC总承包"
    facts = extract_global_facts_from_text(text)
    assert facts["epc_mode"] is not None
