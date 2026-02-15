from app.services.evidence_validator import run_three_gates
from app.services.pricing_guard import detect_pricing_content
from app.extract.tender_parser import parse_tender_requirements


def test_pricing_guard_blocks_pricing_text() -> None:
    blocked, reasons = detect_pricing_content("投标报价合计为 ¥1200000，税率13%")
    assert blocked is True
    assert len(reasons) >= 1


def test_tender_parser_extracts_requirements() -> None:
    text = "第一章 总则。投标人必须具备ISO9001资质。技术评分分值10分。"
    result = parse_tender_requirements(text)
    assert result.status == "OK"
    assert len(result.requirements) >= 2


def test_three_gates_need_human_input_when_sentence_unmatched() -> None:
    result = run_three_gates(
        generated_text="我们拥有国家一级资质并已完成100个项目。",
        evidence_ids=["e1"],
        evidence_texts=["公司具备国家一级资质。"],
    )
    assert result.status == "NEED_HUMAN_INPUT"
    assert result.missing_sentences


def test_three_gates_supported_when_covered() -> None:
    result = run_three_gates(
        generated_text="公司具备国家一级资质。",
        evidence_ids=["e1"],
        evidence_texts=["公司具备国家一级资质，并长期维护该认证。"],
        requirement_mapped=10,
        requirement_total=10,
        coverage_threshold=0.9,
    )
    assert result.status == "SUPPORTED"
    assert result.coverage == 1.0
