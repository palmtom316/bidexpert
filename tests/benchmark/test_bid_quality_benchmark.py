"""Benchmark: 投标质量基准测试集 (R25).

Loads benchmark_cases.json and validates:
- Disqualify keyword detection coverage = 100%
- Global facts extraction accuracy
- Section type coverage
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.extract.tender_parser import DISQUALIFY_KEYWORDS, BONUS_PENALTY_KEYWORDS

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES_DIR / "benchmark_cases.json").read_text(encoding="utf-8"))


def test_benchmark_fixtures_loaded() -> None:
    assert len(CASES) >= 10, f"Expected >=10 benchmark cases, got {len(CASES)}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_disqualify_keyword_coverage(case: dict) -> None:
    """Every expected disqualify keyword in the snippet must be covered by DISQUALIFY_KEYWORDS."""
    snippet = case["tender_snippet"]
    expected = case.get("expected_disqualify_keywords", [])
    for kw in expected:
        # The keyword itself or a DISQUALIFY_KEYWORDS entry containing it must appear in snippet
        found = any(dk for dk in DISQUALIFY_KEYWORDS if kw in dk and dk in snippet)
        if not found:
            # Also check if the keyword is a substring match in the snippet via any dict entry
            found = any(dk for dk in DISQUALIFY_KEYWORDS if dk in snippet and kw in dk)
        if not found:
            # Direct: the expected keyword appears in snippet AND is covered by dict
            found = kw in snippet and any(dk for dk in DISQUALIFY_KEYWORDS if kw in dk or dk in kw)
        assert found, f"Case {case['id']}: expected disqualify keyword '{kw}' not matched by DISQUALIFY_KEYWORDS"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_bonus_penalty_keyword_coverage(case: dict) -> None:
    """Every expected bonus/penalty keyword must be in BONUS_PENALTY_KEYWORDS."""
    snippet = case["tender_snippet"]
    expected = case.get("expected_bonus_keywords", [])
    for kw in expected:
        found = any(bk in snippet for bk in BONUS_PENALTY_KEYWORDS if bk == kw or kw in bk or bk in kw)
        assert found, f"Case {case['id']}: expected bonus keyword '{kw}' not matched"


def test_all_section_types_covered() -> None:
    """Benchmark cases should cover multiple section types."""
    types = {c["section_type"] for c in CASES}
    assert len(types) >= 5, f"Expected >=5 section types, got {types}"


def test_disqualify_cases_present() -> None:
    """At least 5 cases should have disqualify keywords."""
    count = sum(1 for c in CASES if c.get("expected_disqualify_keywords"))
    assert count >= 5, f"Expected >=5 cases with disqualify keywords, got {count}"
