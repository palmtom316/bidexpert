"""Dynamic knowledge quality scoring, expiry governance, and sampling."""
from __future__ import annotations

import datetime
import math
import random


def compute_quality_score(
    *,
    completeness: float,
    recency_days: int,
    source_reliability: float,
) -> float:
    """Compute a 0-100 quality score based on completeness, recency, and source reliability.

    Weights: completeness 40%, recency 30%, source_reliability 30%.
    Recency decays with a half-life of 365 days.
    """
    completeness = max(0.0, min(1.0, completeness))
    source_reliability = max(0.0, min(1.0, source_reliability))
    recency_days = max(0, recency_days)

    recency_factor = math.exp(-0.693 * recency_days / 365)

    raw = (
        0.40 * completeness
        + 0.30 * recency_factor
        + 0.30 * source_reliability
    )
    return round(max(0.0, min(100.0, raw * 100.0)), 2)


def check_expiry_status(
    *,
    valid_to: str | None,
    warning_days: int = 30,
) -> dict[str, str]:
    """Check document expiry status."""
    if not valid_to:
        return {"status": "unknown", "message": "no expiry date set"}

    try:
        expiry = datetime.date.fromisoformat(valid_to)
    except ValueError:
        return {"status": "unknown", "message": f"invalid date: {valid_to}"}

    today = datetime.date.today()
    days_remaining = (expiry - today).days

    if days_remaining < 0:
        return {"status": "expired", "message": f"expired {-days_remaining} days ago"}
    if days_remaining <= warning_days:
        return {"status": "expiring_soon", "message": f"expires in {days_remaining} days"}
    return {"status": "valid", "message": f"valid for {days_remaining} days"}


def should_sample_for_review(*, sample_ratio: float = 0.15) -> bool:
    """Decide whether a document should be sampled for manual review."""
    sample_ratio = max(0.0, min(1.0, sample_ratio))
    if sample_ratio >= 1.0:
        return True
    if sample_ratio <= 0.0:
        return False
    return random.random() < sample_ratio
