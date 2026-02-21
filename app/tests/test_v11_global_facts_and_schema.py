from __future__ import annotations

from app.validator.llm_contracts import validate_generation_payload


def test_extract_global_facts_with_regex() -> None:
    from app.services.global_facts import extract_global_facts_from_text

    text = "\n".join(
        [
            "项目名称：XX输变电工程",
            "计划工期120天",
            "项目经理：张三，证书编号：A-12345",
            "电压等级110kV",
            "合同金额：1000000元",
        ]
    )

    facts = extract_global_facts_from_text(text)

    assert facts["project_name"] == "XX输变电工程"
    assert facts["total_duration_days"] == 120
    assert facts["project_manager"]["name"] == "张三"
    assert facts["project_manager"]["certificate_no"] == "A-12345"
    assert facts["voltage_level"] == "110kV"


def test_global_fact_conflict_detection() -> None:
    from app.services.global_facts import detect_global_fact_conflicts

    conflicts = detect_global_fact_conflicts(
        {
            "voltage_level": "110kV",
            "total_duration_days": 120,
            "project_manager": {"name": "张三", "certificate_no": "A-1"},
        },
        {
            "voltage_level": "35kV",
            "total_duration_days": 120,
            "project_manager": {"name": "张三", "certificate_no": "A-1"},
        },
    )

    assert "voltage_level" in conflicts


def test_validate_generation_payload_accepts_v11_section_json() -> None:
    payload = validate_generation_payload(
        {
            "section_path": "3.1",
            "content": "本章节内容",
            "covers_req": ["REQ-1"],
            "targets_score": ["SCORE-1"],
            "evidence": [
                {
                    "doc_id": "doc-1",
                    "page_range": {"start_page": 1, "end_page": 2},
                    "chunk_id": "chunk-1",
                }
            ],
            "assumptions": [],
            "risk_flags": [],
        }
    )

    assert payload.content_blocks
    assert payload.content_blocks[0].text == "本章节内容"
