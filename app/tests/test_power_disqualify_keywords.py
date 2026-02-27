"""Power engineering disqualification keywords and risk pattern tests."""
from __future__ import annotations

from app.extract.tender_parser import DISQUALIFY_KEYWORDS, _PROMPT_DESCRIPTION
from app.services.tender_analysis import _RISK_PATTERN, _POWER_ENG_PATTERN


def test_disqualify_keywords_count_above_50():
    assert len(DISQUALIFY_KEYWORDS) >= 50


def test_disqualify_keywords_no_duplicates():
    assert len(DISQUALIFY_KEYWORDS) == len(set(DISQUALIFY_KEYWORDS))


def test_disqualify_category_qualification():
    qual_terms = ["资质不符", "无承装修试资质", "许可证失效", "证书过期"]
    for term in qual_terms:
        assert term in DISQUALIFY_KEYWORDS, f"Missing qualification term: {term}"


def test_disqualify_category_technical():
    tech_terms = ["实质性偏离", "重大偏差", "方案缺失", "未提交调试方案"]
    for term in tech_terms:
        assert term in DISQUALIFY_KEYWORDS, f"Missing technical term: {term}"


def test_disqualify_category_commercial():
    comm_terms = ["围标", "串标", "报价超过最高限价", "未缴纳投标保证金"]
    for term in comm_terms:
        assert term in DISQUALIFY_KEYWORDS, f"Missing commercial term: {term}"


def test_disqualify_category_safety():
    safety_terms = ["安全方案缺失", "未编制专项安全方案", "缺少带电作业安全措施"]
    for term in safety_terms:
        assert term in DISQUALIFY_KEYWORDS, f"Missing safety term: {term}"


def test_disqualify_category_format():
    format_terms = ["未按要求密封", "签章缺失", "授权委托书缺失", "电子签章无效"]
    for term in format_terms:
        assert term in DISQUALIFY_KEYWORDS, f"Missing format term: {term}"


def test_prompt_description_mentions_power_engineering():
    assert "电力工程" in _PROMPT_DESCRIPTION or "输变电" in _PROMPT_DESCRIPTION


def test_risk_pattern_matches_power_terms():
    power_risk_terms = ["带电作业违规", "越级跳闸", "设备损坏"]
    for term in power_risk_terms:
        assert _RISK_PATTERN.search(term), f"_RISK_PATTERN should match: {term}"


def test_power_eng_pattern_matches_equipment():
    equipment_terms = ["变电站", "GIS", "变压器", "断路器", "继电保护"]
    for term in equipment_terms:
        assert _POWER_ENG_PATTERN.search(term), f"_POWER_ENG_PATTERN should match: {term}"
