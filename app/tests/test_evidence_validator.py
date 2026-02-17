from __future__ import annotations

from rapidfuzz import fuzz

from app.core.config import settings
from app.services.evidence_validator import gate2_deterministic_check


def test_gate2_uses_configurable_fuzzy_threshold(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    generated = "系统支持自动化投标方案生成与审查流程"
    evidence = "系统支持自动化投标流程"
    base_score = int(fuzz.partial_ratio(generated, evidence))

    monkeypatch.setattr(settings, "evidence_fuzzy_partial_ratio_threshold", base_score + 1, raising=False)
    strict_missing = gate2_deterministic_check(generated, [evidence])
    assert strict_missing

    monkeypatch.setattr(settings, "evidence_fuzzy_partial_ratio_threshold", max(0, base_score - 1), raising=False)
    relaxed_missing = gate2_deterministic_check(generated, [evidence])
    assert not relaxed_missing
