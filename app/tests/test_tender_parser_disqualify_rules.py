"""Task 4: 招标解析领域化 — tests.

Covers:
- R07: regex fallback must recognize disqualification/bonus/penalty keywords
- R06: build_tender_parsing_prompt must include domain-specific parsing guidance
"""
from __future__ import annotations

from app.extract.tender_parser import _parse_with_regex
from app.llm.prompt_suite_v11 import build_tender_parsing_prompt


# ---------------------------------------------------------------------------
# R07: regex fallback keyword expansion
# ---------------------------------------------------------------------------

def test_regex_catches_disqualify_as_waste_bid() -> None:
    text = "投标人未按要求提交保证金的，否则作废标处理。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch disqualification clause"
    assert reqs[0].is_must is True


def test_regex_catches_qualification_rejection() -> None:
    text = "未提供有效营业执照的，不予通过资格审查。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch qualification rejection"


def test_regex_catches_cancel_bid_qualification() -> None:
    text = "提供虚假材料的，取消投标资格。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch cancel bid qualification"


def test_regex_catches_bonus_item() -> None:
    text = "具有类似工程业绩的，加分项，加2分。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch bonus item"


def test_regex_catches_priority_consideration() -> None:
    text = "具有本地化服务能力的投标人优先考虑。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch priority consideration"


def test_regex_catches_deduction_clause() -> None:
    text = "每延误一天扣减合同价款的0.5%。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch deduction clause"


def test_regex_catches_penalty_clause() -> None:
    text = "违反安全规定的，处以罚款并记入不良记录。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch penalty clause"


def test_regex_catches_bid_rejection() -> None:
    text = "投标文件未密封的，拒绝接收。"
    reqs = _parse_with_regex(text)
    assert len(reqs) >= 1, "Should catch bid rejection"


# ---------------------------------------------------------------------------
# R06: build_tender_parsing_prompt domain guidance
# ---------------------------------------------------------------------------

def test_tender_parsing_prompt_has_qualification_guidance() -> None:
    prompt = build_tender_parsing_prompt("test")
    assert "资格审查" in prompt or "资审" in prompt


def test_tender_parsing_prompt_has_commercial_guidance() -> None:
    prompt = build_tender_parsing_prompt("test")
    assert "商务" in prompt


def test_tender_parsing_prompt_has_technical_guidance() -> None:
    prompt = build_tender_parsing_prompt("test")
    assert "技术" in prompt


def test_tender_parsing_prompt_has_scoring_guidance() -> None:
    prompt = build_tender_parsing_prompt("test")
    assert "评标" in prompt or "评分" in prompt


def test_tender_parsing_prompt_has_disqualify_extraction() -> None:
    prompt = build_tender_parsing_prompt("test")
    assert "废标" in prompt or "否决" in prompt or "disqualif" in prompt.lower()
