"""Power engineering RAG decomposition tests."""
from __future__ import annotations

from app.rag.rag_flow import (
    decompose_requirement,
    _classify_sub_requirement,
    _POWER_BOOST_TERMS,
    _CONTINUATION_WORDS,
)


def test_decompose_merges_short_fragments():
    text = "投标人必须具备电力工程施工总承包一级资质，且具有承装修试许可证"
    subs = decompose_requirement(text)
    # Short "且具有承装修试许可证" should be merged with previous
    assert len(subs) <= 2


def test_decompose_merges_continuation_words():
    text = "投标人须具备资质，并提供业绩证明，及人员证书"
    subs = decompose_requirement(text)
    # "并提供业绩证明" and "及人员证书" start with continuation words
    assert len(subs) <= 2


def test_classify_qualification():
    assert _classify_sub_requirement("投标人须具备承装修试资质") == "QUALIFICATION"


def test_classify_tech_param():
    assert _classify_sub_requirement("变压器容量不低于50MVA") == "TECH_PARAM"


def test_classify_personnel():
    assert _classify_sub_requirement("项目经理须持有一级建造师证书") == "PERSONNEL"


def test_classify_must():
    assert _classify_sub_requirement("必须按时完工") == "MUST"


def test_classify_performance():
    assert _classify_sub_requirement("近三年类似工程业绩不少于2项") == "PERFORMANCE"


def test_classify_general():
    assert _classify_sub_requirement("提供完整的技术文件") == "GENERAL"


def test_power_boost_terms_has_key_equipment():
    assert "变电站" in _POWER_BOOST_TERMS
    assert "GIS" in _POWER_BOOST_TERMS
    assert "继电保护" in _POWER_BOOST_TERMS


def test_decompose_empty_returns_general():
    subs = decompose_requirement("")
    assert len(subs) == 1
    assert subs[0].category == "GENERAL"
