"""Task 5: 全局事实扩容 — tests.

Covers:
- R08: GlobalFacts schema must have 15+ fields
- R08: build_global_facts_prompt must reference extended fields
- R08: detect_global_fact_conflicts must cover new fields
- R08: regex extraction must recognize new field patterns
"""
from __future__ import annotations

from app.services.global_facts import (
    GlobalFacts,
    extract_global_facts_from_text,
    detect_global_fact_conflicts,
)
from app.llm.prompt_suite_v11 import build_global_facts_prompt


# ---------------------------------------------------------------------------
# Schema field count
# ---------------------------------------------------------------------------

def test_global_facts_has_at_least_15_fields() -> None:
    """GlobalFacts must have >= 15 fields (was 5)."""
    fields = GlobalFacts.model_fields
    assert len(fields) >= 15, f"Only {len(fields)} fields, need >= 15"


# ---------------------------------------------------------------------------
# New fields exist on schema
# ---------------------------------------------------------------------------

EXPECTED_NEW_FIELDS = [
    "construction_unit",
    "supervision_unit",
    "design_unit",
    "quality_standard",
    "safety_level",
    "subcontract_restriction",
    "milestone_nodes",
    "bid_bond_amount",
    "performance_bond_ratio",
    "project_location",
]


def test_global_facts_has_construction_unit() -> None:
    facts = GlobalFacts(construction_unit="某建设局")
    assert facts.construction_unit == "某建设局"


def test_global_facts_has_supervision_unit() -> None:
    facts = GlobalFacts(supervision_unit="某监理公司")
    assert facts.supervision_unit == "某监理公司"


def test_global_facts_has_quality_standard() -> None:
    facts = GlobalFacts(quality_standard="合格")
    assert facts.quality_standard == "合格"


def test_global_facts_has_safety_level() -> None:
    facts = GlobalFacts(safety_level="省级安全文明工地")
    assert facts.safety_level == "省级安全文明工地"


def test_global_facts_has_bid_bond_amount() -> None:
    facts = GlobalFacts(bid_bond_amount=500000.0)
    assert facts.bid_bond_amount == 500000.0


def test_global_facts_has_project_location() -> None:
    facts = GlobalFacts(project_location="北京市朝阳区")
    assert facts.project_location == "北京市朝阳区"


# ---------------------------------------------------------------------------
# Regex extraction for new fields
# ---------------------------------------------------------------------------

def test_extract_construction_unit_from_text() -> None:
    text = "项目名称：某道路工程\n建设单位：北京市交通委员会\n工期：180天"
    result = extract_global_facts_from_text(text)
    assert result.get("construction_unit") is not None


def test_extract_quality_standard_from_text() -> None:
    text = "项目名称：某工程\n质量标准：合格\n工期：90天"
    result = extract_global_facts_from_text(text)
    assert result.get("quality_standard") is not None


def test_extract_bid_bond_from_text() -> None:
    text = "项目名称：某工程\n投标保证金：50万元\n工期：120天"
    result = extract_global_facts_from_text(text)
    assert result.get("bid_bond_amount") is not None


def test_extract_project_location_from_text() -> None:
    text = "项目名称：某工程\n工程地点：北京市海淀区\n工期：60天"
    result = extract_global_facts_from_text(text)
    assert result.get("project_location") is not None


# ---------------------------------------------------------------------------
# build_global_facts_prompt covers new fields
# ---------------------------------------------------------------------------

def test_global_facts_prompt_has_construction_unit() -> None:
    prompt = build_global_facts_prompt("test")
    assert "construction_unit" in prompt or "建设单位" in prompt


def test_global_facts_prompt_has_quality_standard() -> None:
    prompt = build_global_facts_prompt("test")
    assert "quality_standard" in prompt or "质量标准" in prompt


def test_global_facts_prompt_has_bid_bond() -> None:
    prompt = build_global_facts_prompt("test")
    assert "bid_bond" in prompt or "保证金" in prompt


# ---------------------------------------------------------------------------
# Conflict detection covers new fields
# ---------------------------------------------------------------------------

def test_conflict_detection_catches_construction_unit_mismatch() -> None:
    base = {"construction_unit": "单位A", "project_name": "X"}
    candidate = {"construction_unit": "单位B", "project_name": "X"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert "construction_unit" in conflicts


def test_conflict_detection_catches_quality_standard_mismatch() -> None:
    base = {"quality_standard": "合格", "project_name": "X"}
    candidate = {"quality_standard": "优良", "project_name": "X"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert "quality_standard" in conflicts


def test_conflict_detection_catches_project_location_mismatch() -> None:
    base = {"project_location": "北京", "project_name": "X"}
    candidate = {"project_location": "上海", "project_name": "X"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert "project_location" in conflicts
