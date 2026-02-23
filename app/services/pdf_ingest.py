from __future__ import annotations

import io
import re
from dataclasses import dataclass

from app.core.config import settings
from app.extract.tender_parser import parse_tender_requirements
from app.schemas.contracts import DocBlockItem, IngestUploadResponse
from app.services.adapters.ocr import OCRRuntimeCredential, create_ocr_adapter, normalize_ocr_provider
from app.services.pricing_guard import detect_pricing_content

SECTION_PATTERN = re.compile(r"^\s*(第[一二三四五六七八九十0-9]+[章节条款]|\d+(?:\.\d+)+)")
TABLE_ROW_PATTERN = re.compile(r"\|.+\|")


def _looks_like_table(paragraph: str) -> bool:
    lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
    if not lines:
        return False

    if any(TABLE_ROW_PATTERN.search(line) for line in lines):
        return True

    separators = sum(1 for line in lines if "\t" in line)
    if separators >= 2:
        return True

    wide_columns = 0
    for line in lines:
        columns = [part for part in re.split(r"\s{2,}", line) if part]
        if len(columns) >= 3:
            wide_columns += 1
    return wide_columns >= 2


@dataclass
class PageExtract:
    page_no: int
    text: str
    ocr_used: bool
    source: str = "pypdf"
    image_count: int = 0
    text_len: int = 0
    non_whitespace_ratio: float = 0.0
    ocr_confidence: float | None = None
    needs_manual_review: bool = False


def _non_whitespace_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(re.sub(r"\s+", "", text)) / max(1, len(text))


def _extract_image_count(page) -> int:  # noqa: ANN001
    try:
        return len(list(page.images))
    except Exception:  # noqa: BLE001
        return 0


def _extract_with_pypdf(pdf_bytes: bytes) -> list[PageExtract]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[PageExtract] = []
    for idx, page in enumerate(reader.pages, start=1):
        txt = page.extract_text() or ""
        pages.append(
            PageExtract(
                page_no=idx,
                text=txt.strip(),
                ocr_used=False,
                source="pypdf",
                image_count=_extract_image_count(page),
                text_len=len(txt),
                non_whitespace_ratio=_non_whitespace_ratio(txt),
            )
        )
    return pages


def _ocr_page_with_fitz(pdf_bytes: bytes, page_no: int, dpi: int | None = None) -> str:
    import fitz
    import pytesseract
    from PIL import Image

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(page_no - 1)
    pix = page.get_pixmap(dpi=max(96, int(dpi or settings.pdf_render_dpi)))
    image = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(image, lang="chi_sim+eng")
    return text.strip()


def _render_page_png(pdf_bytes: bytes, page_no: int, dpi: int | None = None) -> bytes:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(page_no - 1)
    pix = page.get_pixmap(dpi=max(96, int(dpi or settings.pdf_render_dpi)))
    return pix.tobytes("png")


def _resolve_effective_ocr_provider(ocr_provider: str | None) -> str:
    normalized = normalize_ocr_provider(ocr_provider, default=settings.ocr_provider or "tesseract")
    if normalized in {"", "local"}:
        return "tesseract"
    return normalized


def _estimate_local_ocr_confidence(text: str) -> float:
    normalized = str(text or "").strip()
    if not normalized:
        return 0.35
    length_score = min(len(normalized) / 220.0, 1.0)
    density_score = min(len(re.sub(r"\s+", "", normalized)) / 180.0, 1.0)
    return max(0.35, min(0.9, 0.45 + 0.35 * length_score + 0.20 * density_score))


def _ocr_page_with_configured_provider(
    pdf_bytes: bytes,
    page_no: int,
    dpi: int | None = None,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> str:
    image_bytes = _render_page_png(pdf_bytes, page_no, dpi)
    runtime_credential = None
    if any(value is not None and str(value).strip() for value in (ocr_api_key, ocr_base_url, ocr_model)):
        runtime_credential = OCRRuntimeCredential(
            api_key=(ocr_api_key or "").strip() or None,
            base_url=(ocr_base_url or "").strip() or None,
            model=(ocr_model or "").strip() or None,
        )
    adapter = create_ocr_adapter(
        _resolve_effective_ocr_provider(ocr_provider),
        runtime_credential=runtime_credential,
    )
    text = adapter.extract_image_bytes(image_bytes, page_no=page_no)
    return text.strip()


def extract_pages_v2(
    pdf_bytes: bytes,
    enable_ocr_fallback: bool = True,
    dpi: int | None = None,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> list[PageExtract]:
    pages = _extract_with_pypdf(pdf_bytes)
    if not enable_ocr_fallback:
        return pages

    text_len_threshold = max(1, int(settings.pdf_ocr_textlen_threshold))
    non_ws_threshold = max(0.0, float(settings.pdf_ocr_min_non_whitespace_ratio))
    confidence_threshold = max(0.0, min(1.0, float(settings.pdf_ocr_confidence_threshold)))
    render_dpi = max(96, int(dpi or settings.pdf_render_dpi))
    provider = _resolve_effective_ocr_provider(ocr_provider)

    extracted: list[PageExtract] = []
    for page in pages:
        text_len = int(page.text_len or len(page.text or ""))
        non_ws_ratio = float(page.non_whitespace_ratio or _non_whitespace_ratio(page.text or ""))
        trigger_ocr = text_len < text_len_threshold or non_ws_ratio < non_ws_threshold
        if not trigger_ocr:
            extracted.append(
                PageExtract(
                    page_no=page.page_no,
                    text=page.text,
                    ocr_used=False,
                    source=page.source or "pypdf",
                    image_count=page.image_count,
                    text_len=text_len,
                    non_whitespace_ratio=non_ws_ratio,
                    ocr_confidence=None,
                    needs_manual_review=False,
                )
            )
            continue

        try:
            page_source = f"pypdf+ocr:{provider}"
            ocr_confidence = 0.0
            if provider in {"tesseract", "local", ""}:
                ocr_text = _ocr_page_with_fitz(pdf_bytes, page.page_no, render_dpi)
                ocr_confidence = _estimate_local_ocr_confidence(ocr_text)
            else:
                try:
                    remote_kwargs: dict[str, str] = {}
                    if (ocr_api_key or "").strip():
                        remote_kwargs["ocr_api_key"] = (ocr_api_key or "").strip()
                    if (ocr_base_url or "").strip():
                        remote_kwargs["ocr_base_url"] = (ocr_base_url or "").strip()
                    if (ocr_model or "").strip():
                        remote_kwargs["ocr_model"] = (ocr_model or "").strip()
                    ocr_text = _ocr_page_with_configured_provider(
                        pdf_bytes,
                        page.page_no,
                        render_dpi,
                        ocr_provider=provider,
                        **remote_kwargs,
                    )
                    ocr_confidence = min(0.98, _estimate_local_ocr_confidence(ocr_text) + 0.08)
                except Exception:  # noqa: BLE001
                    ocr_text = _ocr_page_with_fitz(pdf_bytes, page.page_no, render_dpi)
                    ocr_confidence = _estimate_local_ocr_confidence(ocr_text)
                    page_source = "pypdf+ocr:tesseract"
            needs_manual_review = ocr_confidence < confidence_threshold
            extracted.append(
                PageExtract(
                    page_no=page.page_no,
                    text=ocr_text,
                    ocr_used=True,
                    source=page_source,
                    image_count=page.image_count,
                    text_len=len(ocr_text),
                    non_whitespace_ratio=_non_whitespace_ratio(ocr_text),
                    ocr_confidence=ocr_confidence,
                    needs_manual_review=needs_manual_review,
                )
            )
        except Exception:
            extracted.append(
                PageExtract(
                    page_no=page.page_no,
                    text=page.text,
                    ocr_used=False,
                    source=page.source or "pypdf",
                    image_count=page.image_count,
                    text_len=text_len,
                    non_whitespace_ratio=non_ws_ratio,
                    ocr_confidence=None,
                    needs_manual_review=False,
                )
            )
    return extracted


def extract_pages(pdf_bytes: bytes, enable_ocr_fallback: bool = True) -> list[PageExtract]:
    return extract_pages_v2(
        pdf_bytes,
        enable_ocr_fallback=enable_ocr_fallback,
        dpi=settings.pdf_render_dpi,
    )


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
            block_type = "TABLE" if _looks_like_table(para) else "PARA"
            blocks.append(
                DocBlockItem(
                    page_no=page.page_no,
                    block_type=block_type,
                    section_anchor=current_anchor,
                    content_text=para,
                    char_start=start,
                    char_end=end,
                )
            )
    return blocks


def ingest_pdf_bytes(filename: str, pdf_bytes: bytes, enable_ocr_fallback: bool = True) -> IngestUploadResponse:
    pages = extract_pages_v2(pdf_bytes, enable_ocr_fallback=enable_ocr_fallback, dpi=settings.pdf_render_dpi)
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
