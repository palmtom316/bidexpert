from __future__ import annotations

import hashlib
import re

from app.schemas.contracts import EvidenceUpsertItem


def _split_paragraphs(content_md: str) -> list[str]:
    parts = [item.strip() for item in re.split(r"\n{2,}", content_md) if item.strip()]
    if parts:
        return parts
    line_parts = [item.strip() for item in re.split(r"[。；;]", content_md) if item.strip()]
    return line_parts or [content_md.strip()]


def _chunk_id(outline_id: str, section_key: str, paragraph_no: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]
    return f"fb-{outline_id[:8]}-{section_key}-{paragraph_no}-{digest}"


def standardize_section_feedback_chunks(
    *,
    outline_id: str,
    section_key: str,
    section_title: str,
    content_md: str,
    industry_tag: str | None,
) -> list[EvidenceUpsertItem]:
    paragraphs = _split_paragraphs(content_md)
    chunks: list[EvidenceUpsertItem] = []
    for paragraph_no, text in enumerate(paragraphs, start=1):
        chunks.append(
            EvidenceUpsertItem(
                chunk_id=_chunk_id(outline_id, section_key, paragraph_no, text),
                text=text,
                doc_type="SECTION_FEEDBACK",
                section_type=section_title,
                industry_tag=industry_tag,
                source_locator={
                    "origin": "confirmed_section_feedback",
                    "outline_id": outline_id,
                    "section_key": section_key,
                    "paragraph_no": paragraph_no,
                },
            )
        )
    return chunks
