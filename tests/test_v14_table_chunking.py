"""Unit tests for v1.4 Table-Aware Chunking."""
from __future__ import annotations

import pytest

from app.services.expert_chunking import (
    _extract_table_header,
    _is_parameter_table,
    _split_table_with_header,
    chunk_sections_for_rag,
    estimate_text_tokens,
)


class TestExtractTableHeader:
    def test_standard_markdown_table(self):
        table = "| 型号 | 容量 | 电压 |\n|---|---|---|\n| S11-630 | 630kVA | 10kV |"
        headers = _extract_table_header(table)
        assert headers == ["型号", "容量", "电压"]

    def test_empty_table(self):
        assert _extract_table_header("") == []

    def test_non_table_text(self):
        assert _extract_table_header("just some text") == []

    def test_single_column(self):
        table = "| 参数 |\n|---|\n| 值1 |"
        headers = _extract_table_header(table)
        assert headers == ["参数"]


class TestIsParameterTable:
    def test_parameter_keywords(self):
        assert _is_parameter_table(["型号", "容量", "电压"]) is True
        assert _is_parameter_table(["参数", "值", "单位"]) is True
        assert _is_parameter_table(["规格", "数量"]) is True

    def test_non_parameter_table(self):
        assert _is_parameter_table(["序号", "姓名", "职务"]) is False
        assert _is_parameter_table(["日期", "天气", "温度"]) is False

    def test_empty_headers(self):
        assert _is_parameter_table([]) is False

    def test_mixed_headers_with_parameter(self):
        assert _is_parameter_table(["项目", "额定电流", "备注"]) is True


class TestSplitTableWithHeader:
    def test_small_table_no_split(self):
        table = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
        result = _split_table_with_header(table, max_tokens=100)
        assert len(result) == 1
        text, headers, is_param = result[0]
        assert "| A | B |" in text
        assert headers == ["A", "B"]

    def test_large_table_splits(self):
        header = "| 型号 | 容量kVA | 电压kV |"
        sep = "|---|---|---|"
        rows = [f"| S11-{i} | {i*100} | 10 |" for i in range(50)]
        table = "\n".join([header, sep] + rows)
        # Very small budget to force splitting
        result = _split_table_with_header(table, max_tokens=20)
        assert len(result) > 1
        # Each chunk should have the header prepended
        for text, headers, is_param in result:
            assert "| 型号 | 容量kVA | 电压kV |" in text
            assert "|---|---|---|" in text
            assert is_param is True

    def test_no_separator_single_chunk(self):
        table = "| A | B |\n| 1 | 2 |"
        result = _split_table_with_header(table, max_tokens=100)
        assert len(result) == 1


class TestChunkSectionsTableAware:
    def _make_section(self, table_md: str, text_blocks: list[str] | None = None) -> dict:
        blocks = []
        if text_blocks:
            for t in text_blocks:
                blocks.append({"type": "text", "text": t, "page": 1})
        blocks.append({"type": "table", "table_md": table_md, "page": 1})
        return {
            "section_id": "sec-test",
            "title": "Test Section",
            "page_start": 1,
            "meta": {"section_type": "TEST", "discipline": "GENERAL", "confidence": 0.9},
            "blocks": blocks,
        }

    def test_small_table_single_chunk(self):
        table = "| 型号 | 容量 |\n|---|---|\n| A | 100 |"
        section = self._make_section(table)
        chunks = chunk_sections_for_rag(
            doc_id="test-doc",
            sections=[section],
            industry_tag="power",
            doc_type="EXPERT",
            min_tokens=1,
            max_tokens=500,
        )
        table_chunks = [c for c in chunks if c.chunk_kind == "table"]
        assert len(table_chunks) == 1
        assert table_chunks[0].chunk_kind == "table"
        assert table_chunks[0].table_header == ["型号", "容量"]
        assert table_chunks[0].is_parameter_table is True

    def test_large_table_splits_with_headers(self, monkeypatch):
        # Override settings to force a very small table token budget
        from app.core import config
        monkeypatch.setattr(config.settings, "table_chunk_max_tokens", 20)

        header = "| 序号 | 电压等级 | 备注 |"
        sep = "|---|---|---|"
        rows = [f"| {i} | {i*10}kV | 测试 |" for i in range(100)]
        table = "\n".join([header, sep] + rows)
        section = self._make_section(table)
        chunks = chunk_sections_for_rag(
            doc_id="test-doc",
            sections=[section],
            industry_tag="power",
            doc_type="EXPERT",
            min_tokens=1,
            max_tokens=2000,
        )
        table_chunks = [c for c in chunks if c.chunk_kind == "table"]
        assert len(table_chunks) > 1
        for tc in table_chunks:
            assert tc.chunk_kind == "table"
            # Each sub-chunk should have header prepended
            assert "| 序号 | 电压等级 | 备注 |" in tc.text

    def test_text_chunks_have_no_table_kind(self):
        section = {
            "section_id": "sec-text",
            "title": "Text Section",
            "page_start": 1,
            "meta": {"section_type": "TEXT", "discipline": "GENERAL", "confidence": 0.9},
            "blocks": [{"type": "text", "text": "这是一段纯文本内容", "page": 1}],
        }
        chunks = chunk_sections_for_rag(
            doc_id="test-doc",
            sections=[section],
            industry_tag="power",
            doc_type="EXPERT",
            min_tokens=1,
            max_tokens=500,
        )
        for c in chunks:
            assert c.chunk_kind is None  # text chunks don't set chunk_kind
