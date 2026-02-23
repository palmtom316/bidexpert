from __future__ import annotations


def test_prompt_suite_contains_required_templates() -> None:
    from app.llm.prompt_suite_v11 import (
        CLAUDE_PROMPT_TEMPERATURE,
        GENERAL_RULES,
        build_global_facts_prompt,
        build_review_prompt,
        build_section_generation_prompt,
        build_tender_parsing_prompt,
    )

    assert "只输出合法 JSON" in GENERAL_RULES
    assert "不得与 Global Facts 冲突" in GENERAL_RULES

    parsing = build_tender_parsing_prompt("demo")
    assert "mandatory_requirements" in parsing
    assert "scoring_items" in parsing
    assert "资审" in parsing
    assert "商务" in parsing
    assert "技术" in parsing
    assert "评标" in parsing
    assert "废标条款" in parsing
    assert "资格否决" in parsing

    facts = build_global_facts_prompt("demo")
    assert "project_name" in facts
    assert "contract_amount" in facts
    assert "construction_unit" in facts
    assert "supervision_unit" in facts
    assert "quality_standard" in facts
    assert "safety_civilization_level" in facts
    assert "subcontracting_limit" in facts
    assert "schedule_milestones" in facts
    assert "bid_bond_amount" in facts

    section = build_section_generation_prompt(
        global_facts_json={"project_name": "x"},
        relevant_requirements=["r1"],
        relevant_scoring=["s1"],
        top_chunks=[{"chunk_id": "c1"}],
    )
    assert "section_path" in section
    assert "risk_flags" in section

    review = build_review_prompt({"section_path": "3.1"})
    assert "overall_risk" in review

    assert CLAUDE_PROMPT_TEMPERATURE["tender_parsing"] <= 0.2
    assert CLAUDE_PROMPT_TEMPERATURE["global_facts"] == 0.0
