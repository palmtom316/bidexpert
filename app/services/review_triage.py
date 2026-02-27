"""Three-tier review triage gate for bid compliance."""
from __future__ import annotations

from typing import Any


def triage_review_result(report: dict[str, Any]) -> dict[str, Any]:
    """Classify a review report into PASS / REVIEW / REWRITE tiers.

    Thresholds:
    - REWRITE: status==FAIL, any high-severity issue, or coverage < 0.75
    - REVIEW: medium-severity issues, inconsistencies, warnings, or coverage < 0.90
    - PASS: everything else (clean or low-severity only)
    """
    status = str(report.get("status", "")).upper()
    modeled_issues = report.get("modeled_issues", []) or []
    inconsistencies = report.get("logical_inconsistencies", []) or []
    coverage = float(report.get("coverage_estimate", 1.0))

    has_high = any(
        str(issue.get("severity", "")).lower() == "high"
        for issue in modeled_issues
        if isinstance(issue, dict)
    )
    has_medium = any(
        str(issue.get("severity", "")).lower() == "medium"
        for issue in modeled_issues
        if isinstance(issue, dict)
    )

    # REWRITE tier
    if status == "FAIL" or has_high or coverage < 0.75:
        reasons = []
        if status == "FAIL":
            reasons.append("review status is FAIL")
        if has_high:
            reasons.append("high-severity issues found")
        if coverage < 0.75:
            reasons.append(f"coverage too low ({coverage:.2%})")
        return {"tier": "REWRITE", "reason": "; ".join(reasons)}

    # REVIEW tier
    if has_medium or inconsistencies or status == "WARN" or coverage < 0.90:
        reasons = []
        if has_medium:
            reasons.append("medium-severity issues found")
        if inconsistencies:
            reasons.append(f"{len(inconsistencies)} logical inconsistencies")
        if status == "WARN":
            reasons.append("review status is WARN")
        if coverage < 0.90:
            reasons.append(f"coverage below threshold ({coverage:.2%})")
        return {"tier": "REVIEW", "reason": "; ".join(reasons)}

    # PASS tier
    return {"tier": "PASS", "reason": "all checks passed"}
