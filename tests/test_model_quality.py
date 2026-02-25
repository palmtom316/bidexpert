"""Tests for app.services.model_quality — compliance quality scoring."""
from __future__ import annotations

import pytest

from app.services.model_quality import evaluate_compliance_quality


class TestEvaluateComplianceQuality:
    def test_perfect_pass(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={"coverage_estimate": 1.0},
        )
        assert score == 100.0

    def test_zero_coverage_pass(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={"coverage_estimate": 0.0},
        )
        assert score == 22.0  # 0*78 + 22 - 0

    def test_fail_status_zero_coverage(self):
        score = evaluate_compliance_quality(
            status="FAIL",
            report={"coverage_estimate": 0.0},
        )
        assert score == 0.0

    def test_warn_status(self):
        score = evaluate_compliance_quality(
            status="WARN",
            report={"coverage_estimate": 1.0},
        )
        assert score == 90.0  # 78 + 12

    def test_unknown_status_gets_default(self):
        score = evaluate_compliance_quality(
            status="UNKNOWN",
            report={"coverage_estimate": 1.0},
        )
        assert score == 84.0  # 78 + 6

    def test_issue_penalty_modeled(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={
                "coverage_estimate": 1.0,
                "modeled_issues": [{"desc": "a"}, {"desc": "b"}],
            },
        )
        # 78 + 22 - min(36, 2*4) = 100 - 8 = 92
        assert score == 92.0

    def test_issue_penalty_missing(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={
                "coverage_estimate": 1.0,
                "missing_requirements": ["a", "b", "c"],
            },
        )
        # 78 + 22 - min(36, 3*3) = 100 - 9 = 91
        assert score == 91.0

    def test_issue_penalty_risk(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={
                "coverage_estimate": 1.0,
                "risk_points": ["r1", "r2"],
            },
        )
        # 78 + 22 - min(36, 2*1) = 100 - 2 = 98
        assert score == 98.0

    def test_penalty_capped_at_36(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={
                "coverage_estimate": 1.0,
                "modeled_issues": [{}] * 20,
            },
        )
        # penalty = min(36, 20*4) = 36; score = 100 - 36 = 64
        assert score == 64.0

    def test_none_report(self):
        score = evaluate_compliance_quality(status="PASS", report=None)
        assert score == 22.0  # 0*78 + 22

    def test_non_dict_report(self):
        score = evaluate_compliance_quality(status="PASS", report="bad")
        assert score == 22.0

    def test_score_clamped_to_zero(self):
        score = evaluate_compliance_quality(
            status="FAIL",
            report={
                "coverage_estimate": 0.0,
                "modeled_issues": [{}] * 10,
            },
        )
        assert score == 0.0

    def test_coverage_clamped_above_one(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={"coverage_estimate": 5.0},
        )
        # coverage clamped to 1.0 → 78 + 22 = 100
        assert score == 100.0

    def test_non_numeric_coverage(self):
        score = evaluate_compliance_quality(
            status="PASS",
            report={"coverage_estimate": "bad"},
        )
        assert score == 22.0  # defaults to 0.0 coverage

    def test_return_type_is_float(self):
        score = evaluate_compliance_quality(status="PASS", report={})
        assert isinstance(score, float)
