from __future__ import annotations

from app.services.methodology.types import RiskAssessment

_ALLOWED_SOURCE_TYPES = {"public_doc", "training", "sample"}


def assess_source_risk(
    *,
    source_type: str,
    findings: list[dict] | list[str],
    pii_removed: bool = True,
) -> RiskAssessment:
    normalized_source = (source_type or "").strip().lower()

    if normalized_source not in _ALLOWED_SOURCE_TYPES:
        return RiskAssessment(
            risk_level="high",
            blocked=True,
            blocking_gate="L0",
            reasons=["source_type_unknown_or_unauthorized"],
        )

    if not pii_removed:
        return RiskAssessment(
            risk_level="high",
            blocked=True,
            blocking_gate="L1",
            reasons=["pii_not_removed"],
        )

    if findings:
        return RiskAssessment(
            risk_level="medium",
            blocked=False,
            blocking_gate="PASS",
            reasons=["contains_sensitive_patterns_but_sanitized"],
        )

    return RiskAssessment(
        risk_level="low",
        blocked=False,
        blocking_gate="PASS",
        reasons=[],
    )
