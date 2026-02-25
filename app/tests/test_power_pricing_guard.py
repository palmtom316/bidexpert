"""Power engineering pricing guard adaptation tests."""
from __future__ import annotations

from app.services.pricing_guard import (
    PRICING_CONTEXT_KEYWORDS,
    POWER_UNIT_WHITELIST,
    POWER_TECH_PATTERN,
    _strip_power_tech_numbers,
    detect_pricing_content,
)


def test_pricing_context_has_power_fee_terms():
    power_fees = ["措施费", "调试费", "检测费", "监理费"]
    for term in power_fees:
        assert term in PRICING_CONTEXT_KEYWORDS, f"Missing: {term}"


def test_power_unit_whitelist_has_electrical_units():
    assert "kV" in POWER_UNIT_WHITELIST
    assert "MVA" in POWER_UNIT_WHITELIST
    assert "MW" in POWER_UNIT_WHITELIST


def test_power_tech_pattern_matches_voltage():
    assert POWER_TECH_PATTERN.search("110kV")
    assert POWER_TECH_PATTERN.search("50MVA")


def test_strip_power_tech_numbers():
    text = "变压器容量50MVA，电压110kV，导线截面240mm2"
    stripped = _strip_power_tech_numbers(text)
    assert "50MVA" not in stripped
    assert "110kV" not in stripped
    assert "240mm2" not in stripped


def test_tech_params_dont_trigger_pricing_false_positive():
    # Pure technical specification text with many numbers but no pricing context
    text = (
        "本工程电压等级为220kV，变压器容量为120MVA，"
        "导线截面为300mm2，设计风速为27m/s，"
        "海拔高度为1200m，接地电阻不大于0.5Ω"
    )
    blocked, reasons = detect_pricing_content(text)
    assert not blocked, f"Technical params should not trigger pricing: {reasons}"
