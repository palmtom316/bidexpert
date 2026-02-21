from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document as WordDocument
from docx.document import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.extract.tender_parser import parse_tender_requirements
from app.schemas.contracts import DocBlockItem, IngestUploadResponse
from app.services.pricing_guard import detect_pricing_content

HEADING_STYLE_PATTERN = re.compile(r"^heading\s*[1-9]?", re.IGNORECASE)


def _iter_docx_blocks(document: DocxDocument):  # noqa: ANN202
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            yield Paragraph(child, document)
        elif child.tag.endswith("}tbl"):
            yield Table(child, document)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _paragraph_block_type(paragraph: Paragraph, text: str) -> str:
    style_name = str(getattr(paragraph.style, "name", "") or "").strip()
    style_name_lower = style_name.lower()
    if HEADING_STYLE_PATTERN.match(style_name):
        return "TITLE"
    if any(token in style_name_lower for token in ("list", "bullet", "number", "编号", "项目符号")):
        return "LIST"
    if re.match(r"^\s*([-*•]|\d+[\.)、])\s+", text):
        return "LIST"
    return "PARA"


def extract_docx_blocks(filename: str, content: bytes) -> list[DocBlockItem]:
    try:
        document = WordDocument(io.BytesIO(content))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid .docx content") from exc

    blocks: list[DocBlockItem] = []
    current_anchor = (Path(filename).stem or "未命名章节").strip()[:48] or "未命名章节"
    cursor = 0

    for node in _iter_docx_blocks(document):
        if isinstance(node, Paragraph):
            text = _normalize_text(node.text)
            if not text:
                continue

            block_type = _paragraph_block_type(node, text)
            if block_type == "TITLE":
                current_anchor = text[:48] or current_anchor

            start = cursor
            end = cursor + len(text)
            cursor = end + 1
            blocks.append(
                DocBlockItem(
                    page_no=1,
                    block_type=block_type,
                    section_anchor=current_anchor,
                    content_text=text,
                    char_start=start,
                    char_end=end,
                )
            )
            continue

        if isinstance(node, Table):
            rows: list[list[str]] = []
            for row in node.rows:
                cells = [_normalize_text(cell.text) for cell in row.cells]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            table_text = "\n".join(" | ".join(cell or "-" for cell in row) for row in rows)
            start = cursor
            end = cursor + len(table_text)
            cursor = end + 1
            blocks.append(
                DocBlockItem(
                    page_no=1,
                    block_type="TABLE",
                    section_anchor=current_anchor,
                    content_text=table_text,
                    char_start=start,
                    char_end=end,
                )
            )

    return blocks


def ingest_docx_bytes(filename: str, docx_bytes: bytes) -> IngestUploadResponse:
    blocks = extract_docx_blocks(filename, docx_bytes)
    full_text = "\n".join((block.content_text or "") for block in blocks if block.content_text)

    blocked, reasons = detect_pricing_content(full_text)
    if blocked:
        return IngestUploadResponse(
            status=f"BLOCKED_PRICING_CONTENT: {'; '.join(reasons)}",
            filename=filename,
            page_count=1,
            blocks=[],
            requirements=[],
        )

    parsed = parse_tender_requirements(full_text)
    return IngestUploadResponse(
        status=parsed.status,
        filename=filename,
        page_count=1,
        blocks=blocks,
        requirements=parsed.requirements,
    )
