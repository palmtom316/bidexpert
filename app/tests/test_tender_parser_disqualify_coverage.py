"""Task 15: 废标条款覆盖率测试 (R24).

Verifies that DISQUALIFY_KEYWORDS covers all known disqualification patterns.
"""
from __future__ import annotations

from app.extract.tender_parser import DISQUALIFY_KEYWORDS, BONUS_PENALTY_KEYWORDS


KNOWN_DISQUALIFY_PHRASES = [
    "废标",
    "否决投标",
    "不予通过",
    "取消投标资格",
    "取消中标资格",
    "拒绝接收",
    "拒绝投标",
    "资格审查",
]

KNOWN_BONUS_PENALTY_PHRASES = [
    "加分",
    "优先考虑",
    "优先",
    "扣减",
    "扣分",
    "罚款",
    "处罚",
]


def test_all_known_disqualify_phrases_in_keywords() -> None:
    for phrase in KNOWN_DISQUALIFY_PHRASES:
        assert phrase in DISQUALIFY_KEYWORDS, f"Missing disqualify keyword: {phrase}"


def test_all_known_bonus_penalty_phrases_in_keywords() -> None:
    for phrase in KNOWN_BONUS_PENALTY_PHRASES:
        assert phrase in BONUS_PENALTY_KEYWORDS, f"Missing bonus/penalty keyword: {phrase}"


def test_disqualify_keywords_not_empty() -> None:
    assert len(DISQUALIFY_KEYWORDS) >= 7


def test_bonus_penalty_keywords_not_empty() -> None:
    assert len(BONUS_PENALTY_KEYWORDS) >= 6


def test_no_duplicate_disqualify_keywords() -> None:
    assert len(DISQUALIFY_KEYWORDS) == len(set(DISQUALIFY_KEYWORDS))


def test_no_duplicate_bonus_penalty_keywords() -> None:
    assert len(BONUS_PENALTY_KEYWORDS) == len(set(BONUS_PENALTY_KEYWORDS))
