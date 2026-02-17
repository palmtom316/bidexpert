from __future__ import annotations

from typing import Any


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def evaluate_compliance_quality(*, status: str, report: dict[str, Any] | None) -> float:
    payload = report if isinstance(report, dict) else {}
    coverage = _clamp(_as_float(payload.get("coverage_estimate"), default=0.0), 0.0, 1.0)

    modeled_issues = payload.get("modeled_issues", [])
    modeled_issue_count = len(modeled_issues) if isinstance(modeled_issues, list) else 0
    missing = payload.get("missing_requirements", [])
    missing_count = len(missing) if isinstance(missing, list) else 0
    risk_points = payload.get("risk_points", [])
    risk_count = len(risk_points) if isinstance(risk_points, list) else 0

    issue_penalty = min(36.0, modeled_issue_count * 4.0 + missing_count * 3.0 + risk_count * 1.0)
    status_score = {
        "PASS": 22.0,
        "WARN": 12.0,
        "FAIL": 0.0,
    }.get(str(status).upper(), 6.0)

    score = coverage * 78.0 + status_score - issue_penalty
    return round(_clamp(score, 0.0, 100.0), 2)


__all__ = ["evaluate_compliance_quality"]
