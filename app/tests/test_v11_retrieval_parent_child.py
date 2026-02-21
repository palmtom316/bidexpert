from __future__ import annotations

from app.services.expert_chunking import chunk_sections_for_rag
from app.services.qdrant_store import RetrievedEvidence


def test_chunking_emits_parent_child_metadata() -> None:
    sections = [
        {
            "section_id": "sec-100",
            "title": "第三章 技术方案",
            "meta": {"section_type": "TECH", "discipline": "ELECTRICAL", "confidence": 0.9},
            "blocks": [
                {"type": "text", "page": 2, "text": "投标人必须提供110kV设备安装方案。" * 120},
                {"type": "table", "page": 3, "table_md": "|型号|参数|\n|XH-110|合格|"},
            ],
        }
    ]

    chunks = chunk_sections_for_rag(doc_id="doc-parent", sections=sections, industry_tag="power", doc_type="EXPERT")

    assert chunks
    for item in chunks:
        locator = item.source_locator or {}
        assert locator.get("parent_chunk_id")
        assert locator.get("anchor_type") in {"paragraph", "table", "clause"}


def test_key_fact_filter_prefers_voltage_consistency() -> None:
    from app.services import qdrant_store

    hits = [
        RetrievedEvidence(
            chunk_id="a",
            score=0.9,
            text="本方案适用于35kV线路改造项目。",
            payload={},
        ),
        RetrievedEvidence(
            chunk_id="b",
            score=0.8,
            text="本方案适用于110kV变电站工程。",
            payload={},
        ),
    ]

    filtered = qdrant_store._apply_key_fact_filter(query="110kV 项目实施方案", items=hits)

    assert [item.chunk_id for item in filtered] == ["b"]
