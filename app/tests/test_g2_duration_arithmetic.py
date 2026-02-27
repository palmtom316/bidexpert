"""Tests for G2.6 duration arithmetic hard validation."""
from __future__ import annotations


from app.schemas.contracts import RedlineCheckRequest, RedlineDurationCheck
from app.services.redline_engine import _build_duration_findings, run_redline_check


# ── _build_duration_findings unit tests ──────────────────────


def test_duration_mismatch_returns_p0():
    check = RedlineDurationCheck(
        committed_duration_days=100,
        start_date="2025-03-01",
        completion_date="2025-06-01",  # 92 days, not 100
    )
    findings = _build_duration_findings(check)
    match = [f for f in findings if f.rule_id == "DURATION-MISMATCH"]
    assert len(match) == 1
    assert match[0].severity == "P0"
    assert "100" in match[0].message
    assert "92" in match[0].message


def test_duration_match_passes():
    check = RedlineDurationCheck(
        committed_duration_days=92,
        start_date="2025-03-01",
        completion_date="2025-06-01",  # exactly 92 days
    )
    findings = _build_duration_findings(check)
    assert len(findings) == 0


def test_duration_too_short_returns_p0():
    check = RedlineDurationCheck(
        committed_duration_days=60,
        start_date="2025-03-01",
        completion_date="2025-04-30",  # 60 days
        min_required_duration_days=90,
    )
    findings = _build_duration_findings(check)
    too_short = [f for f in findings if f.rule_id == "DURATION-TOO-SHORT"]
    assert len(too_short) == 1
    assert too_short[0].severity == "P0"
    assert "60" in too_short[0].message
    assert "90" in too_short[0].message


def test_duration_meets_minimum_passes():
    check = RedlineDurationCheck(
        committed_duration_days=92,
        start_date="2025-03-01",
        completion_date="2025-06-01",
        min_required_duration_days=90,
    )
    findings = _build_duration_findings(check)
    assert len(findings) == 0


def test_duration_invalid_date_returns_p0():
    check = RedlineDurationCheck(
        committed_duration_days=100,
        start_date="not-a-date",
        completion_date="2025-06-01",
    )
    findings = _build_duration_findings(check)
    assert len(findings) == 1
    assert findings[0].rule_id == "DURATION-DATE-INVALID"
    assert findings[0].severity == "P0"


def test_duration_completion_before_start_returns_p0():
    check = RedlineDurationCheck(
        committed_duration_days=100,
        start_date="2025-06-01",
        completion_date="2025-03-01",
    )
    findings = _build_duration_findings(check)
    assert len(findings) == 1
    assert findings[0].rule_id == "DURATION-DATE-ORDER"
    assert findings[0].severity == "P0"


def test_duration_completion_equals_start_returns_p0():
    check = RedlineDurationCheck(
        committed_duration_days=0,
        start_date="2025-06-01",
        completion_date="2025-06-01",
    )
    findings = _build_duration_findings(check)
    assert len(findings) == 1
    assert findings[0].rule_id == "DURATION-DATE-ORDER"


# ── Integration: run_redline_check with duration_check ───────


def test_run_redline_check_with_duration_mismatch_blocks():
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
        duration_check=RedlineDurationCheck(
            committed_duration_days=100,
            start_date="2025-03-01",
            completion_date="2025-06-01",
        ),
    )
    report = run_redline_check(payload)
    assert report.status == "BLOCKED"
    assert any(f.rule_id == "DURATION-MISMATCH" for f in report.findings)


def test_run_redline_check_without_duration_check_passes():
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
        duration_check=None,
    )
    report = run_redline_check(payload)
    assert report.status == "PASS"
    assert len(report.findings) == 0
