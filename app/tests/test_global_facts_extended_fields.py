from __future__ import annotations

from app.services.global_facts import detect_global_fact_conflicts, extract_global_facts_from_text


def test_extract_global_facts_supports_extended_fields() -> None:
    text = "\n".join(
        [
            "项目名称：XX输变电工程",
            "项目编号：XM-2026-01",
            "建设单位：国家电网XX公司",
            "监理单位：XX监理有限公司",
            "计划工期120天",
            "关键节点：30天完成基础，60天完成主体，120天竣工验收",
            "质量标准：合格并达到优良标准",
            "安全文明等级：省级安全文明工地",
            "分包限制：主体工程不得分包",
            "投标保证金：500000元",
            "履约保证金：1000000元",
            "质保期24个月",
            "税率13%",
            "项目经理：张三，证书编号：A-12345",
            "电压等级110kV",
            "合同金额：1000000元",
        ]
    )

    facts = extract_global_facts_from_text(text)

    assert facts["project_name"] == "XX输变电工程"
    assert facts["project_code"] == "XM-2026-01"
    assert facts["construction_unit"] == "国家电网XX公司"
    assert facts["supervision_unit"] == "XX监理有限公司"
    assert facts["quality_standard"] == "合格并达到优良标准"
    assert facts["safety_civilization_level"] == "省级安全文明工地"
    assert facts["subcontracting_limit"] == "主体工程不得分包"
    assert facts["schedule_milestones"] == ["30天完成基础", "60天完成主体", "120天竣工验收"]
    assert facts["bid_bond_amount"] == 500000.0
    assert facts["performance_bond_amount"] == 1000000.0
    assert facts["warranty_period_months"] == 24
    assert facts["tax_rate"] == 13.0


def test_global_facts_conflict_detection_covers_extended_fields() -> None:
    base = {
        "quality_standard": "合格",
        "subcontracting_limit": "主体工程不得分包",
        "bid_bond_amount": 500000.0,
        "schedule_milestones": ["30天完成基础", "60天完成主体"],
        "project_manager": {"name": "张三", "certificate_no": "A-12345"},
    }
    candidate = {
        "quality_standard": "优良",
        "subcontracting_limit": "允许专业分包",
        "bid_bond_amount": 300000.0,
        "schedule_milestones": ["30天完成基础", "90天完成主体"],
        "project_manager": {"name": "张三", "certificate_no": "B-99999"},
    }

    conflicts = detect_global_fact_conflicts(base, candidate)
    assert "quality_standard" in conflicts
    assert "subcontracting_limit" in conflicts
    assert "bid_bond_amount" in conflicts
    assert "schedule_milestones" in conflicts
    assert "project_manager.certificate_no" in conflicts
