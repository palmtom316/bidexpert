"""Power engineering evidence validator enhancement tests."""
from __future__ import annotations

from app.services.evidence_validator import (
    _STANDARD_PROTECT,
    _extract_fact_sentences,
    gate2_numerical_consistency,
    gate2_format_elements,
    run_three_gates,
)


def test_standard_protect_pattern_matches():
    assert _STANDARD_PROTECT.search("DL/T 5218-2012")
    assert _STANDARD_PROTECT.search("GB 50150")
    assert _STANDARD_PROTECT.search("GB/T 50064")


def test_extract_fact_sentences_preserves_standards():
    text = "施工应符合DL/T 5218-2012的要求。接地应符合DL/T 621标准。"
    sentences = _extract_fact_sentences(text)
    # Standard references should be preserved intact
    found_std = any("DL/T 5218-2012" in s for s in sentences)
    assert found_std, f"Standard reference lost in: {sentences}"


def test_numerical_consistency_detects_missing():
    req = "变压器容量不低于50MVA，电压等级110kV"
    gen = "本工程采用变压器，电压等级110kV"
    warnings = gate2_numerical_consistency(gen, req)
    assert any("50MVA" in w for w in warnings)


def test_numerical_consistency_no_warning_when_present():
    req = "变压器容量50MVA"
    gen = "采用50MVA变压器"
    warnings = gate2_numerical_consistency(gen, req)
    assert len(warnings) == 0


def test_format_elements_detects_missing():
    gen = "这是一段普通文本"
    warnings = gate2_format_elements(gen, ["表格", "图纸"])
    assert len(warnings) == 2
    assert any("表格" in w for w in warnings)
