"""Tests for app.services.knowledge_standardizer — section feedback chunking."""
from __future__ import annotations

from app.services.knowledge_standardizer import (
    _chunk_id,
    _split_paragraphs,
    standardize_section_feedback_chunks,
)


class TestSplitParagraphs:
    def test_double_newline_split(self):
        text = "段落一\n\n段落二\n\n段落三"
        result = _split_paragraphs(text)
        assert len(result) == 3
        assert result[0] == "段落一"

    def test_no_double_newline_returns_single(self):
        """Without double newlines, text is returned as single paragraph."""
        text = "句子一。句子二；句子三"
        result = _split_paragraphs(text)
        assert len(result) == 1
        assert result[0] == text

    def test_single_text_fallback(self):
        text = "一段没有分隔符的文本"
        result = _split_paragraphs(text)
        assert len(result) == 1
        assert result[0] == text

    def test_strips_whitespace(self):
        text = "  段落一  \n\n  段落二  "
        result = _split_paragraphs(text)
        assert result[0] == "段落一"
        assert result[1] == "段落二"

    def test_empty_parts_filtered(self):
        text = "段落一\n\n\n\n\n段落二"
        result = _split_paragraphs(text)
        assert len(result) == 2


class TestChunkId:
    def test_format(self):
        cid = _chunk_id("outline-12345678", "sec1", 1, "hello")
        assert cid.startswith("fb-outline-")
        assert "-sec1-1-" in cid

    def test_deterministic(self):
        a = _chunk_id("o1", "s1", 1, "text")
        b = _chunk_id("o1", "s1", 1, "text")
        assert a == b

    def test_different_text_different_id(self):
        a = _chunk_id("o1", "s1", 1, "text_a")
        b = _chunk_id("o1", "s1", 1, "text_b")
        assert a != b


class TestStandardizeSectionFeedbackChunks:
    def test_basic_chunking(self):
        chunks = standardize_section_feedback_chunks(
            outline_id="outline-abc",
            section_key="construction_plan",
            section_title="施工组织设计",
            content_md="段落一\n\n段落二",
            industry_tag="power",
        )
        assert len(chunks) == 2
        assert chunks[0].doc_type == "SECTION_FEEDBACK"
        assert chunks[0].section_type == "施工组织设计"
        assert chunks[0].industry_tag == "power"

    def test_source_locator(self):
        chunks = standardize_section_feedback_chunks(
            outline_id="outline-abc",
            section_key="safety_plan",
            section_title="安全方案",
            content_md="内容",
            industry_tag=None,
        )
        loc = chunks[0].source_locator
        assert loc["origin"] == "confirmed_section_feedback"
        assert loc["outline_id"] == "outline-abc"
        assert loc["section_key"] == "safety_plan"
        assert loc["paragraph_no"] == 1

    def test_paragraph_numbering(self):
        chunks = standardize_section_feedback_chunks(
            outline_id="o1",
            section_key="s1",
            section_title="T",
            content_md="A\n\nB\n\nC",
            industry_tag=None,
        )
        numbers = [c.source_locator["paragraph_no"] for c in chunks]
        assert numbers == [1, 2, 3]

    def test_chunk_ids_unique(self):
        chunks = standardize_section_feedback_chunks(
            outline_id="o1",
            section_key="s1",
            section_title="T",
            content_md="段落一\n\n段落二\n\n段落三",
            industry_tag=None,
        )
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))
