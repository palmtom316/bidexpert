from __future__ import annotations

import io
import re
from dataclasses import dataclass

from app.extract.tender_parser import parse_tender_requirements
from app.schemas.contracts import DocBlockItem, IngestUploadResponse
from app.services.pricing_guard import detect_pricing_content

SECTION_PATTERN = re.compile(r"^\s*(第[一二三四五六七八九十0-9]+[章节条款]|\d+(?:\.\d+)+)")


@dataclass
class PageExtract:
    page_no: int
    text: str
    ocr_used: bool


def _extract_with_pypdf(pdf_bytes: bytes) -> list[PageExtract]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[PageExtract] = []
    for idx, page in enumerate(reader.pages, start=1):
        txt = (page.extract_text() or "").strip()
        pages.append(PageExtract(page_no=idx, text=txt, ocr_used=False))
    return pages


def _ocr_page_with_fitz(pdf_bytes: bytes, page_no: int) -> str:
    import fitz
    import pytesseract
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(page_no - 1)
    pix = page.get_pixmap(dpi=220)
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    return text.strip()


def extract_pages(pdf_bytes: bytes, enable_ocr_fallback: bool = True) -> list[PageExtract]:
    pages = _extract_with_pypdf(pdf_bytes)
    if not enable_ocr_fallback:
        return pages

    extracted: list[PageExtract] = []
    for page in pages:
        if len(page.text) >= 40:
            extracted.append(page)
            continue
        try:
            ocr_text = _ocr_page_with_fitz(pdf_bytes, page.page_no)
            extracted.append(PageExtract(page_no=page.page_no, text=ocr_text, ocr_used=True))
        except Exception:
            extracted.append(page)
    return extracted


def build_doc_blocks(pages: list[PageExtract]) -> list[DocBlockItem]:
    blocks: list[DocBlockItem] = []
    for page in pages:
        page_text = page.text or ""
        current_anchor: str | None = None
        cursor = 0

        for para in [p.strip() for p in re.split(r"\n{2,}", page_text) if p.strip()]:
            lines = [x.strip() for x in para.splitlines() if x.strip()]
            if lines:
                anchor_match = SECTION_PATTERN.match(lines[0])
                if anchor_match:
                    current_anchor = lines[0][:48]

            start = cursor
            end = cursor + len(para)
            cursor = end + 1
            blocks.append(
                DocBlockItem(
                    page_no=page.page_no,
                    block_type="PARA",
                    section_anchor=current_anchor,
                    content_text=para,
                    char_start=start,
                    char_end=end,
                )
            )
    return blocks


def ingest_pdf_bytes(filename: str, pdf_bytes: bytes, enable_ocr_fallback: bool = True) -> IngestUploadResponse:
    pages = extract_pages(pdf_bytes, enable_ocr_fallback=enable_ocr_fallback)
    full_text = "\f".join(page.text for page in pages)

    blocked, reasons = detect_pricing_content(full_text)
    if blocked:
        return IngestUploadResponse(
            status=f"BLOCKED_PRICING_CONTENT: {'; '.join(reasons)}",
            filename=filename,
            page_count=len(pages),
            blocks=[],
            requirements=[],
        )

    blocks = build_doc_blocks(pages)
    parsed = parse_tender_requirements(full_text)
    return IngestUploadResponse(
        status=parsed.status,
        filename=filename,
        page_count=len(pages),
        blocks=blocks,
        requirements=parsed.requirements,
    )
