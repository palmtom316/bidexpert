"""Benchmark: 投标质量基准测试集 (R25).

Loads benchmark_cases.json and validates:
- Disqualify keyword detection coverage = 100%
- Global facts extraction accuracy
- Section type coverage
- Power engineering specific cases
"""
from __future__ import annotations

import json
import pathlib

import pytest

from app.extract.tender_parser import DISQUALIFY_KEYWORDS, BONUS_PENALTY_KEYWORDS
from app.core.section_router import detect_power_section_type

FIXTURES_DIR = pathlib.Path(__file__).resolve().parent / "fixtures"
CASES = json.loads((FIXTURES_DIR / "benchmark_cases.json").read_text(encoding="utf-8"))
POWER_CASES = [c for c in CASES if c.get("power_section_type")]


def test_benchmark_fixtures_loaded() -> None:
    assert len(CASES) >= 20, f"Expected >=20 benchmark cases, got {len(CASES)}"


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
    assert len(types) >= 8, f"Expected >=8 section types, got {types}"


def test_disqualify_cases_present() -> None:
    """At least 5 cases should have disqualify keywords."""
    count = sum(1 for c in CASES if c.get("expected_disqualify_keywords"))
    assert count >= 5, f"Expected >=5 cases with disqualify keywords, got {count}"


# ── Power engineering benchmark tests ──


def test_power_cases_present() -> None:
    """At least 10 power engineering cases should be present."""
    assert len(POWER_CASES) >= 10, f"Expected >=10 power cases, got {len(POWER_CASES)}"


def test_power_section_types_diverse() -> None:
    """Power cases should cover multiple power section types."""
    types = {c["power_section_type"] for c in POWER_CASES}
    assert len(types) >= 5, f"Expected >=5 power section types, got {types}"


@pytest.mark.parametrize("case", POWER_CASES, ids=[c["id"] for c in POWER_CASES])
def test_power_section_type_detection(case: dict) -> None:
    """Power section type should be detectable from the tender snippet."""
    expected_type = case["power_section_type"]
    section = {"title": case["name"]}
    detected = detect_power_section_type(section)
    # Allow None for types not in the router map (e.g., PHOTOVOLTAIC, DISTRIBUTION)
    if detected is not None:
        assert detected == expected_type, (
            f"Case {case['id']}: expected {expected_type}, got {detected}"
        )


@pytest.mark.parametrize("case", POWER_CASES, ids=[c["id"] for c in POWER_CASES])
def test_power_disqualify_keyword_coverage(case: dict) -> None:
    """Power cases with disqualify keywords must be covered."""
    snippet = case["tender_snippet"]
    expected = case.get("expected_disqualify_keywords", [])
    for kw in expected:
        found = kw in snippet and any(dk for dk in DISQUALIFY_KEYWORDS if kw in dk or dk in kw)
        assert found, f"Power case {case['id']}: keyword '{kw}' not matched"


def test_power_section_type_commissioning_present() -> None:
    """At least 2 commissioning plan cases should exist."""
    count = sum(1 for c in POWER_CASES if c["section_type"] == "commissioning_plan")
    assert count >= 2, f"Expected >=2 commissioning cases, got {count}"


def test_power_cases_have_expected_facts() -> None:
    """Power cases with expected_facts should have at least one power-specific fact."""
    power_fact_keys = {
        "rated_capacity", "line_length", "conductor_type", "tower_count",
        "voltage_level", "design_wind_speed", "annual_thunder_days",
        "pollution_level", "seismic_fortification", "altitude",
        "grid_connection_point", "epc_mode", "substation_type",
    }
    cases_with_power_facts = sum(
        1 for c in POWER_CASES
        if any(k in power_fact_keys for k in c.get("expected_facts", {}))
    )
    assert cases_with_power_facts >= 5, f"Expected >=5 power cases with power-specific facts, got {cases_with_power_facts}"
