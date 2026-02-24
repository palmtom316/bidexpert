"""Task 7: 三级人工审核门禁 — tests.

Covers:
- R23: triage_review_result classifies review reports into PASS / REVIEW / REWRITE
  - PASS: no high-severity issues, full coverage, no conflicts
  - REVIEW: warnings or medium issues present
  - REWRITE: high-severity issues, missing disqualification coverage, or low coverage
"""
from __future__ import annotations

from app.services.review_triage import triage_review_result


# ---------------------------------------------------------------------------
# PASS tier — auto-approve
# ---------------------------------------------------------------------------

def test_triage_pass_when_clean() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 1.0,
    }
    result = triage_review_result(report)
    assert result["tier"] == "PASS"


def test_triage_pass_with_low_severity_only() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [
            {"severity": "low", "issue_type": "STYLE", "description": "minor formatting"}
        ],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.98,
    }
    result = triage_review_result(report)
    assert result["tier"] == "PASS"


# ---------------------------------------------------------------------------
# REVIEW tier — human review needed
# ---------------------------------------------------------------------------

def test_triage_review_with_medium_issues() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [
            {"severity": "medium", "issue_type": "PARAMETER", "description": "param mismatch"}
        ],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.95,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REVIEW"


def test_triage_review_with_warnings() -> None:
    report = {
        "status": "WARN",
        "modeled_issues": [],
        "missing_requirements": [],
        "logical_inconsistencies": ["工期数据前后不一致"],
        "coverage_estimate": 0.92,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REVIEW"


def test_triage_review_with_borderline_coverage() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [],
        "missing_requirements": ["REQ-0005"],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.88,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REVIEW"


# ---------------------------------------------------------------------------
# REWRITE tier — must redo
# ---------------------------------------------------------------------------

def test_triage_rewrite_with_high_severity() -> None:
    report = {
        "status": "FAIL",
        "modeled_issues": [
            {"severity": "high", "issue_type": "MISSING", "description": "critical req missing"}
        ],
        "missing_requirements": ["REQ-0001"],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.70,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REWRITE"


def test_triage_rewrite_with_very_low_coverage() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [],
        "missing_requirements": ["REQ-0001", "REQ-0002", "REQ-0003"],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.60,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REWRITE"


def test_triage_rewrite_on_fail_status() -> None:
    report = {
        "status": "FAIL",
        "modeled_issues": [],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 0.50,
    }
    result = triage_review_result(report)
    assert result["tier"] == "REWRITE"


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

def test_triage_result_has_reason() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 1.0,
    }
    result = triage_review_result(report)
    assert "reason" in result
    assert isinstance(result["reason"], str)


def test_triage_result_has_tier() -> None:
    report = {
        "status": "PASS",
        "modeled_issues": [],
        "missing_requirements": [],
        "logical_inconsistencies": [],
        "coverage_estimate": 1.0,
    }
    result = triage_review_result(report)
    assert result["tier"] in {"PASS", "REVIEW", "REWRITE"}
