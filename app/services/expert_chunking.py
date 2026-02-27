from __future__ import annotations

import hashlib
import re
from typing import Iterable

from app.core.config import settings
from app.schemas.contracts import EvidenceUpsertItem

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

# v1.4 — Table boundary / header detection patterns
_TABLE_SEPARATOR_RE = re.compile(r"^\|[-:| ]+\|$", re.MULTILINE)
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
_PARAMETER_TABLE_KEYWORDS = {"型号", "容量", "电压", "参数", "规格", "额定", "功率", "电流", "阻抗", "频率"}


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


# ── v1.4 Table-aware chunking helpers ───────────────────────────

def _extract_table_header(table_md: str) -> list[str]:
    """Extract column headers from first row of a markdown table."""
    lines = table_md.strip().split("\n")
    if not lines:
        return []
    first_row = lines[0].strip()
    if not first_row.startswith("|"):
        return []
    cells = [c.strip() for c in first_row.strip("|").split("|")]
    return [c for c in cells if c]


def _is_parameter_table(headers: list[str]) -> bool:
    """Heuristic: check if table headers contain parameter-related keywords."""
    header_text = "".join(headers)
    return any(kw in header_text for kw in _PARAMETER_TABLE_KEYWORDS)


def _split_table_with_header(
    table_md: str,
    max_tokens: int,
) -> list[tuple[str, list[str], bool]]:
    """Split a long markdown table row-by-row, prepending header to each chunk.

    Returns list of (chunk_text, headers, is_param_table).
    """
    lines = table_md.strip().split("\n")
    if len(lines) < 2:
        headers = _extract_table_header(table_md)
        return [(table_md, headers, _is_parameter_table(headers))]

    # Find header row and separator
    separator_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if _TABLE_SEPARATOR_RE.match(line.strip()):
            separator_idx = i
            break

    if separator_idx is None:
        # No separator found — treat as a single chunk
        headers = _extract_table_header(table_md)
        return [(table_md, headers, _is_parameter_table(headers))]

    header_block = "\n".join(lines[: separator_idx + 1])
    data_rows = lines[separator_idx + 1 :]
    headers = _extract_table_header(table_md)
    is_param = _is_parameter_table(headers)

    header_tokens = estimate_text_tokens(header_block)
    row_budget = max(1, max_tokens - header_tokens)

    chunks: list[tuple[str, list[str], bool]] = []
    current_rows: list[str] = []
    current_tokens = 0

    for row in data_rows:
        row_stripped = row.strip()
        if not row_stripped:
            continue
        row_tokens = estimate_text_tokens(row_stripped)

        if current_tokens + row_tokens > row_budget and current_rows:
            chunk_text = header_block + "\n" + "\n".join(current_rows)
            chunks.append((chunk_text, headers, is_param))
            current_rows = []
            current_tokens = 0

        current_rows.append(row_stripped)
        current_tokens += row_tokens

    if current_rows:
        chunk_text = header_block + "\n" + "\n".join(current_rows)
        chunks.append((chunk_text, headers, is_param))

    return chunks if chunks else [(table_md, headers, is_param)]


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
        quality_score = float(meta.get("confidence", 0.8) or 0.8) * 100.0
        quality_score = max(0.0, min(100.0, quality_score))

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
            chunks.append(
                EvidenceUpsertItem(
                    chunk_id=_chunk_id(doc_id, section_id, "text", idx, text),
                    text=text,
                    doc_type=doc_type,
                    section_type=section_type,
                    industry_tag=industry_tag,
                    quality_score=quality_score,
                    source_locator=locator,
                    parent_chunk_id=section_parent_chunk_id,
                    anchor_type="paragraph",
                )
            )

        for idx, (page, table_md) in enumerate(table_blocks, start=1):
            table_parent_chunk_id = f"{doc_id[:8]}-{section_id}-parent-table-{idx}"
            table_max_tok = getattr(settings, "table_chunk_max_tokens", max_tokens)
            table_tok_count = estimate_text_tokens(table_md)

            if table_tok_count <= table_max_tok:
                # Single chunk — fits within budget
                headers = _extract_table_header(table_md)
                is_param = _is_parameter_table(headers)
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
                chunks.append(
                    EvidenceUpsertItem(
                        chunk_id=_chunk_id(doc_id, section_id, "table", idx, table_md),
                        text=table_md,
                        doc_type=doc_type,
                        section_type=section_type,
                        industry_tag=industry_tag,
                        quality_score=quality_score,
                        source_locator=locator,
                        parent_chunk_id=table_parent_chunk_id,
                        anchor_type="table",
                        chunk_kind="table",
                        table_header=headers if headers else None,
                        is_parameter_table=is_param,
                    )
                )
            else:
                # v1.4 — Split long table with header prepending
                sub_chunks = _split_table_with_header(table_md, max_tokens=table_max_tok)
                for sub_idx, (sub_text, headers, is_param) in enumerate(sub_chunks, start=1):
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
                    chunks.append(
                        EvidenceUpsertItem(
                            chunk_id=_chunk_id(doc_id, section_id, "table", idx * 100 + sub_idx, sub_text),
                            text=sub_text,
                            doc_type=doc_type,
                            section_type=section_type,
                            industry_tag=industry_tag,
                            quality_score=quality_score,
                            source_locator=locator,
                            parent_chunk_id=table_parent_chunk_id,
                            anchor_type="table",
                            chunk_kind="table",
                            table_header=headers if headers else None,
                            is_parameter_table=is_param,
                        )
                    )
    return chunks
