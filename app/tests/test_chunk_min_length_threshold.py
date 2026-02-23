from __future__ import annotations

from types import SimpleNamespace

from app.services import expert_enterprise_pipeline
from app.services.expert_library import _fallback_chunks_from_blocks


def test_fallback_chunks_skip_short_text_by_configurable_min_chars(monkeypatch) -> None:
    monkeypatch.setattr("app.services.expert_library.settings.expert_chunk_min_chars", 80, raising=False)

    blocks = [
        SimpleNamespace(content_text="短文本" * 10, page_no=1, block_type="PARA", section_anchor="第一章"),
        SimpleNamespace(content_text="长文本内容" * 25, page_no=2, block_type="PARA", section_anchor="第二章"),
    ]
    chunks = _fallback_chunks_from_blocks(
        blocks=blocks,
        industry_tag="电力",
        doc_type="EXPERT_HISTORY",
        pricing_related=False,
        doc_id="doc-1",
    )

    assert len(chunks) == 1
    assert "长文本内容" in chunks[0].text


def test_enrich_sections_respects_configurable_min_chars(monkeypatch) -> None:
    monkeypatch.setattr(
        expert_enterprise_pipeline,
        "enhance_section_metadata",
        lambda **_: {"summary": "摘要", "confidence": 0.9},
    )
    structure = {
        "sections": [
            {
                "section_id": "S001",
                "title": "第一章",
                "blocks": [{"type": "text", "text": "示例文本" * 10}],
            }
        ]
    }

    monkeypatch.setattr("app.services.expert_enterprise_pipeline.settings.expert_chunk_min_chars", 80, raising=False)
    strict_meta = expert_enterprise_pipeline.enrich_sections_v1(structure)[0]
    assert "信息不足" in strict_meta["summary"]
    assert strict_meta["confidence"] == 0.5

    monkeypatch.setattr("app.services.expert_enterprise_pipeline.settings.expert_chunk_min_chars", 20, raising=False)
    relaxed_meta = expert_enterprise_pipeline.enrich_sections_v1(structure)[0]
    assert "信息不足" not in relaxed_meta["summary"]
    assert relaxed_meta["confidence"] == 0.9
