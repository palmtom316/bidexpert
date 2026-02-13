from app.services.embedding import embed_text
from app.services.pdf_ingest import PageExtract, build_doc_blocks
from app.services.qdrant_store import _is_payload_allowed


def test_embed_text_is_stable_and_normalized() -> None:
    v1 = embed_text("国家一级资质", vector_size=32)
    v2 = embed_text("国家一级资质", vector_size=32)
    assert v1 == v2
    assert len(v1) == 32


def test_build_doc_blocks_extracts_anchor_and_offsets() -> None:
    pages = [PageExtract(page_no=1, text="第一章 总则\n\n投标人必须具备资质。", ocr_used=False)]
    blocks = build_doc_blocks(pages)
    assert len(blocks) == 2
    assert blocks[0].section_anchor is not None
    assert blocks[0].char_end >= blocks[0].char_start


def test_payload_filter_excludes_pricing_sensitive_and_expired() -> None:
    assert _is_payload_allowed({"sensitivity_level": "PUBLIC_OK", "forbidden_tags": []}) is True
    assert _is_payload_allowed({"sensitivity_level": "SENSITIVE", "forbidden_tags": []}) is False
    assert _is_payload_allowed({"sensitivity_level": "PUBLIC_OK", "forbidden_tags": ["PRICING_RELATED"]}) is False
    assert _is_payload_allowed({"sensitivity_level": "PUBLIC_OK", "forbidden_tags": [], "valid_to": "2020-01-01"}) is False
