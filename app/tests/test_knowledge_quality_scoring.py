"""Task 9: 动态质量评分与到期治理 — tests.

Covers:
- R02: Dynamic quality scoring replaces hardcoded 88.0
- R19: Expiry governance — documents near/past expiry get lower scores
- R20: Sampling mechanism — configurable sampling ratio
"""
from __future__ import annotations

import datetime
from app.services.knowledge_quality import (
    compute_quality_score,
    check_expiry_status,
    should_sample_for_review,
)


# ---------------------------------------------------------------------------
# R02: Dynamic quality scoring
# ---------------------------------------------------------------------------

def test_quality_score_is_not_hardcoded_88() -> None:
    score = compute_quality_score(
        completeness=0.9,
        recency_days=30,
        source_reliability=0.8,
    )
    assert score != 88.0, "Score must not be hardcoded 88.0"
    assert 0.0 <= score <= 100.0


def test_quality_score_higher_for_complete_recent_reliable() -> None:
    high = compute_quality_score(completeness=1.0, recency_days=10, source_reliability=1.0)
    low = compute_quality_score(completeness=0.5, recency_days=365, source_reliability=0.3)
    assert high > low


def test_quality_score_decreases_with_age() -> None:
    recent = compute_quality_score(completeness=0.9, recency_days=30, source_reliability=0.8)
    old = compute_quality_score(completeness=0.9, recency_days=730, source_reliability=0.8)
    assert recent > old


def test_quality_score_increases_with_completeness() -> None:
    full = compute_quality_score(completeness=1.0, recency_days=60, source_reliability=0.8)
    partial = compute_quality_score(completeness=0.3, recency_days=60, source_reliability=0.8)
    assert full > partial


def test_quality_score_clamps_to_range() -> None:
    score = compute_quality_score(completeness=0.0, recency_days=9999, source_reliability=0.0)
    assert 0.0 <= score <= 100.0
    score2 = compute_quality_score(completeness=1.0, recency_days=0, source_reliability=1.0)
    assert 0.0 <= score2 <= 100.0


# ---------------------------------------------------------------------------
# R19: Expiry governance
# ---------------------------------------------------------------------------

def test_expiry_status_valid() -> None:
    future = (datetime.date.today() + datetime.timedelta(days=90)).isoformat()
    status = check_expiry_status(valid_to=future)
    assert status["status"] == "valid"


def test_expiry_status_expiring_soon() -> None:
    soon = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()
    status = check_expiry_status(valid_to=soon, warning_days=30)
    assert status["status"] == "expiring_soon"


def test_expiry_status_expired() -> None:
    past = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    status = check_expiry_status(valid_to=past)
    assert status["status"] == "expired"


def test_expiry_status_no_date() -> None:
    status = check_expiry_status(valid_to=None)
    assert status["status"] == "unknown"


# ---------------------------------------------------------------------------
# R20: Sampling mechanism
# ---------------------------------------------------------------------------

def test_sampling_respects_ratio() -> None:
    results = [should_sample_for_review(sample_ratio=1.0) for _ in range(20)]
    assert all(results), "100% sample ratio should always return True"


def test_sampling_zero_ratio_never_samples() -> None:
    results = [should_sample_for_review(sample_ratio=0.0) for _ in range(20)]
    assert not any(results), "0% sample ratio should never return True"
