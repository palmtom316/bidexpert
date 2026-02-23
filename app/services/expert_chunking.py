from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.schemas.contracts import EvidenceUpsertItem
from app.services.knowledge_quality import score_knowledge_quality

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def estimate_text_tokens(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text or ""))


def _to_token_slices(text: str, max_tokens: int, overlap_tokens: int = 0) -> list[str]:
    tokens = TOKEN_PATTERN.findall(text)
    if not tokens:
        return []
    step = max_tokens - overlap_tokens
    if step <= 0:
        raise ValueError("overlap_tokens must be less than max_tokens")
    parts: list[str] = []
    cursor = 0
    while cursor < len(tokens):
        parts.append(" ".join(tokens[cursor : cursor + max_tokens]))
        cursor += step
    return parts


def _page_marker(pages: Iterable[int]) -> int | str:
    values = sorted({int(p) for p in pages if p is not None})
    if not values:
        return 1
    if len(values) == 1:
        return values[0]
    return f"{values[0]}-{values[-1]}"


def _chunk_id(doc_id: str, section_id: str, block_type: str, index: int, text: str) -> str:
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
    return f"{doc_id[:8]}-{section_id}-{block_type}-{index}-{digest}"


def _chunk_locator(
    *,
    doc_id: str,
    section: dict,
    section_type: str,
    discipline: str,
    source_page: int | str,
    block_type: str,
    parent_chunk_id: str | None,
    anchor_type: str,
    parent_context: str | None,
) -> dict:
    meta = section.get("meta", {}) or {}
    return {
        "doc_id": doc_id,
        "section_id": str(section.get("section_id", "")),
        "section_type": section_type,
        "discipline": discipline,
        "project_phase": meta.get("project_phase"),
        "reusability": meta.get("reusability"),
        "source_page": source_page,
        "section_title": section.get("title"),
        "block_type": block_type,
        "parent_chunk_id": parent_chunk_id,
        "anchor_type": anchor_type,
        "parent_context": parent_context,
    }


def _split_text_blocks(
    *,
    text_blocks: list[tuple[int, str]],
    min_tokens: int,
    max_tokens: int,
    overlap_tokens: int = 0,
) -> list[tuple[str, int | str]]:
    chunks: list[tuple[str, int | str]] = []
    buffer_parts: list[str] = []
    buffer_pages: list[int] = []
    buffer_tokens = 0

    def flush_buffer() -> None:
        nonlocal buffer_tokens
        if not buffer_parts:
            return
        chunks.append(("\n\n".join(buffer_parts).strip(), _page_marker(buffer_pages)))
        buffer_parts.clear()
        buffer_pages.clear()
        buffer_tokens = 0

    for page_no, text in text_blocks:
        cleaned = (text or "").strip()
        if not cleaned:
            continue

        count = estimate_text_tokens(cleaned)
        if count > max_tokens:
            flush_buffer()
            for piece in _to_token_slices(cleaned, max_tokens=max_tokens, overlap_tokens=overlap_tokens):
                if piece:
                    chunks.append((piece, page_no))
            continue

        if buffer_tokens > 0 and (buffer_tokens + count) > max_tokens:
            flush_buffer()

        buffer_parts.append(cleaned)
        buffer_pages.append(page_no)
        buffer_tokens += count

        if buffer_tokens >= min_tokens:
            flush_buffer()

    flush_buffer()
    return chunks


def chunk_sections_for_rag(
    *,
    doc_id: str,
    sections: list[dict],
    industry_tag: str | None,
    doc_type: str,
    min_tokens: int = 800,
    max_tokens: int = 1200,
    overlap_tokens: int = 0,
) -> list[EvidenceUpsertItem]:
    if min_tokens <= 0 or max_tokens <= 0:
        raise ValueError("min_tokens and max_tokens must be positive")
    if min_tokens > max_tokens:
        raise ValueError("min_tokens must be less than or equal to max_tokens")
    if overlap_tokens < 0:
        raise ValueError("overlap_tokens must be non-negative")
    if overlap_tokens >= max_tokens:
        raise ValueError("overlap_tokens must be less than max_tokens")

    chunks: list[EvidenceUpsertItem] = []
    for section in sections:
        section_id = str(section.get("section_id") or "sec-unknown")
        section_title = str(section.get("title") or section_id)
        meta = section.get("meta", {}) or {}
        section_type = str(meta.get("section_type") or section_title)
        discipline = str(meta.get("discipline") or "GENERAL")
        confidence = float(meta.get("confidence", 0.8) or 0.8)
        confidence = max(0.0, min(1.0, confidence))
        match_terms = [str(item).strip() for item in (meta.get("keywords") or []) if str(item).strip()]

        text_blocks: list[tuple[int, str]] = []
        table_blocks: list[tuple[int, str]] = []
        for block in section.get("blocks", []):
            block_type = str(block.get("type", "text")).lower()
            page = int(block.get("page") or section.get("page_start") or 1)
            if block_type == "table":
                table_md = (block.get("table_md") or block.get("text") or "").strip()
                if table_md:
                    table_blocks.append((page, table_md))
            else:
                text = (block.get("text") or "").strip()
                if text:
                    text_blocks.append((page, text))

        section_parent_context = "\n\n".join(text for _, text in text_blocks).strip() or None
        section_parent_chunk_id = f"{doc_id[:8]}-{section_id}-parent-text"

        text_fragments = _split_text_blocks(
            text_blocks=text_blocks,
            min_tokens=min_tokens,
            max_tokens=max_tokens,
            overlap_tokens=overlap_tokens,
        )
        for idx, (text, source_page) in enumerate(text_fragments, start=1):
            quality = score_knowledge_quality(
                text=text,
                source="enterprise_extract",
                industry_tag=industry_tag,
                confidence=confidence,
                category_key=section_type,
                match_terms=match_terms,
            )
            locator = _chunk_locator(
                doc_id=doc_id,
                section=section,
                section_type=section_type,
                discipline=discipline,
                source_page=source_page,
                block_type="text",
                parent_chunk_id=section_parent_chunk_id,
                anchor_type="paragraph",
                parent_context=section_parent_context,
            )
            locator["quality_signals"] = {
                "timeliness": quality.timeliness,
                "completeness": quality.completeness,
                "relevance": quality.relevance,
                "source_reliability": quality.source_reliability,
                "expiry_status": quality.expiry_status,
            }
            chunks.append(
                EvidenceUpsertItem(
                    chunk_id=_chunk_id(doc_id, section_id, "text", idx, text),
                    text=text,
                    doc_type=doc_type,
                    section_type=section_type,
                    industry_tag=industry_tag,
                    valid_to=quality.valid_to,
                    quality_score=quality.score,
                    source_locator=locator,
                    parent_chunk_id=section_parent_chunk_id,
                    anchor_type="paragraph",
                )
            )

        for idx, (page, table_md) in enumerate(table_blocks, start=1):
            table_parent_chunk_id = f"{doc_id[:8]}-{section_id}-parent-table-{idx}"
            quality = score_knowledge_quality(
                text=table_md,
                source="enterprise_table",
                industry_tag=industry_tag,
                confidence=confidence,
                category_key=section_type,
                match_terms=match_terms,
            )
            locator = _chunk_locator(
                doc_id=doc_id,
                section=section,
                section_type=section_type,
                discipline=discipline,
                source_page=page,
                block_type="table",
                parent_chunk_id=table_parent_chunk_id,
                anchor_type="table",
                parent_context=table_md,
            )
            locator["quality_signals"] = {
                "timeliness": quality.timeliness,
                "completeness": quality.completeness,
                "relevance": quality.relevance,
                "source_reliability": quality.source_reliability,
                "expiry_status": quality.expiry_status,
            }
            chunks.append(
                EvidenceUpsertItem(
                    chunk_id=_chunk_id(doc_id, section_id, "table", idx, table_md),
                    text=table_md,
                    doc_type=doc_type,
                    section_type=section_type,
                    industry_tag=industry_tag,
                    valid_to=quality.valid_to,
                    quality_score=quality.score,
                    source_locator=locator,
                    parent_chunk_id=table_parent_chunk_id,
                    anchor_type="table",
                )
            )
    return chunks
