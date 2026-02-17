from __future__ import annotations

from app.schemas.contracts import ParsedRequirement
from app.services import tender_analysis



def test_insights_from_parsed_requirements_include_compliance_and_scoring() -> None:
    items = [
        ParsedRequirement(
            requirement_id="REQ-001",
            original_text="投标人必须达到10分并按格式提交文件。",
            page_no=3,
            section_anchor="第三章 评分办法",
            is_must=True,
            score_weight=10.0,
            format_constraints={"format_required": True},
        )
    ]

    insights = tender_analysis._insights_from_parsed_requirements(items)
    categories = {item.category.value for item in insights}

    assert "COMPLIANCE_REQUIREMENTS" in categories
    assert "SCORING_POINTS" in categories
    assert "BIDDING_POINTS" in categories



def test_insights_from_parsed_requirements_empty_when_no_items() -> None:
    assert tender_analysis._insights_from_parsed_requirements([]) == []
