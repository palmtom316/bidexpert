from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SanitizeResult:
    sanitized_text: str
    pii_removed: bool
    findings: list[dict] = field(default_factory=list)


@dataclass
class RiskAssessment:
    risk_level: str
    blocked: bool
    blocking_gate: str
    reasons: list[str] = field(default_factory=list)


@dataclass
class SimilarityAssessment:
    score: float
    threshold: float
    decision: str
