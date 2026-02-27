"""Clause cross-reference extraction tests."""
from __future__ import annotations

from app.extract.tender_parser import extract_cross_references


def test_extract_chapter_reference():
    refs = extract_cross_references("详见第三章技术条款")
    assert len(refs) >= 1
    assert any("第三章" in r for r in refs)


def test_extract_appendix_reference():
    refs = extract_cross_references("按照附录A的要求执行")
    assert len(refs) >= 1
    assert any("附录A" in r for r in refs)


def test_extract_multiple_references():
    text = "详见第五章，并参见附件B"
    refs = extract_cross_references(text)
    assert len(refs) >= 2


def test_no_cross_references():
    refs = extract_cross_references("投标人须具备一级资质")
    assert len(refs) == 0
