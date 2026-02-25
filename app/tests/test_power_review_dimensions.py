"""Power engineering review engine dimension tests."""
from __future__ import annotations

from app.services.review_engine import (
    _check_standard_references,
    _check_numerical_consistency,
    _STANDARD_PATTERN,
    _KNOWN_CURRENT_STANDARDS,
)


def test_standard_pattern_matches_gb():
    assert _STANDARD_PATTERN.search("符合GB 50150标准要求")


def test_standard_pattern_matches_dl():
    assert _STANDARD_PATTERN.search("按照DL/T 5218执行")


def test_known_standards_has_power_entries():
    assert "GB 50150" in _KNOWN_CURRENT_STANDARDS
    assert "DL/T 621" in _KNOWN_CURRENT_STANDARDS
    assert "DL/T 878" in _KNOWN_CURRENT_STANDARDS


def test_check_standard_references_known_no_issue():
    text = "施工应符合GB 50150电气试验标准"
    issues = _check_standard_references(text)
    # GB 50150 is known, should not flag
    known_flagged = [i for i in issues if "50150" in i.get("location", "")]
    assert len(known_flagged) == 0


def test_check_standard_references_unknown_flags():
    text = "须符合GB 99999标准"
    issues = _check_standard_references(text)
    assert len(issues) >= 1
    assert issues[0]["issue_type"] == "STANDARD_UNVERIFIED"


def test_check_numerical_consistency_no_conflict():
    text = "本工程电压等级为110kV"
    facts = {"voltage_level": "110kV"}
    issues = _check_numerical_consistency(text, facts)
    assert len(issues) == 0


def test_check_numerical_consistency_detects_mismatch():
    text = "本工程涉及500kV线路施工"
    facts = {"voltage_level": "220kV"}
    issues = _check_numerical_consistency(text, facts)
    assert any(i["issue_type"] == "NUMERICAL_INCONSISTENT" for i in issues)
