from __future__ import annotations

from app.extract import tender_parser
from app.schemas.contracts import ParsedRequirement
from app.models.tables import TenderKeyCategory
from app.services.tender_analysis import _insights_from_parsed_requirements


def test_regex_fallback_extracts_disqualify_and_bonus_rules(monkeypatch) -> None:
    monkeypatch.setattr(tender_parser, "_parse_with_llm", lambda _: [])

    text = (
        "投标文件未按要求密封的，否则作废标处理。"
        "存在重大偏差的，不予通过资格审查。"
        "发现弄虚作假行为的，取消投标资格。"
        "采用节能设备可加分2分。"
        "同等条件下优先考虑本地化服务团队。"
    )

    result = tender_parser.parse_tender_requirements(text)
    assert result.status == "OK"

    disqualify_rules = [item for item in result.requirements if item.format_constraints.get("disqualify_rule")]
    bonus_rules = [
        item
        for item in result.requirements
        if item.format_constraints.get("scoring_rule_type") == "bonus"
    ]

    assert any("作废标" in item.original_text for item in disqualify_rules)
    assert any("资格审查" in item.original_text for item in disqualify_rules)
    assert any("取消投标资格" in item.original_text for item in disqualify_rules)
    assert any("加分" in item.original_text for item in bonus_rules)
    assert any("优先考虑" in item.original_text for item in bonus_rules)


def test_tender_analysis_distinguishes_disqualify_and_penalty_rules() -> None:
    parsed = [
        ParsedRequirement(
            requirement_id="REQ-0001",
            original_text="未按要求提交保证金的，作废标处理。",
            page_no=1,
            section_anchor="资格审查",
            is_must=True,
            score_weight=None,
            format_constraints={"disqualify_rule": True},
        ),
        ParsedRequirement(
            requirement_id="REQ-0002",
            original_text="关键技术参数偏离每项扣2分。",
            page_no=2,
            section_anchor="评分办法",
            is_must=False,
            score_weight=2.0,
            format_constraints={"scoring_rule_type": "penalty"},
        ),
    ]

    insights = _insights_from_parsed_requirements(parsed)

    assert any(
        item.category == TenderKeyCategory.RISK_ALERTS and "作废标" in item.content
        for item in insights
    )
    assert any(
        item.category == TenderKeyCategory.SCORING_POINTS and "扣2分" in item.content
        for item in insights
    )
    assert not any(
        item.category == TenderKeyCategory.RISK_ALERTS and "扣2分" in item.content
        for item in insights
    )
