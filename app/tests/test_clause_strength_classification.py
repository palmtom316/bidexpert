"""Clause strength classification tests."""
from __future__ import annotations

from app.extract.tender_parser import ClauseStrength, classify_clause_strength


def test_disqualify_level():
    assert classify_clause_strength("未提供资质将否决投标") == ClauseStrength.DISQUALIFY
    assert classify_clause_strength("废标条件") == ClauseStrength.DISQUALIFY


def test_reject_level():
    assert classify_clause_strength("实质性偏离将不予受理") == ClauseStrength.REJECT
    assert classify_clause_strength("资质不符的投标人") == ClauseStrength.REJECT


def test_deduct_level():
    assert classify_clause_strength("每延误一天扣1分") == ClauseStrength.DEDUCT
    assert classify_clause_strength("违约金按合同价的0.5%") == ClauseStrength.DEDUCT


def test_advisory_level():
    assert classify_clause_strength("建议提供ISO认证") == ClauseStrength.ADVISORY
    assert classify_clause_strength("宜采用环保材料") == ClauseStrength.ADVISORY
