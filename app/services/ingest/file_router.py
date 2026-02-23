from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.contracts import DocBlockItem, IngestUploadResponse
from app.services.adapters.ocr import normalize_ocr_provider
from app.services.ingest.docx_ingest import extract_docx_blocks, ingest_docx_bytes
from app.services.pdf_ingest import PageExtract, build_doc_blocks, extract_pages_v2, ingest_pdf_bytes

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@dataclass
class IngestedUploadPayload:
    blocks: list[DocBlockItem]
    page_count: int
    source_format: str
    content_type: str
    parser_version: str
    full_text: str
    page_meta: dict[int, dict[str, object]] = field(default_factory=dict)


def _pdf_payload(
    file_bytes: bytes,
    enable_ocr_fallback: bool,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> IngestedUploadPayload:
    pages: list[PageExtract] = extract_pages_v2(
        file_bytes,
        enable_ocr_fallback=enable_ocr_fallback,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
    )
    blocks = build_doc_blocks(pages)
    full_text = "\f".join(page.text for page in pages)
    source_format = "scanned_pdf" if any(page.ocr_used for page in pages) else "pdf"
    page_meta = {
        int(page.page_no): {
            "source": page.source or ("pypdf+ocr:tesseract" if page.ocr_used else "pypdf"),
            "ocr_used": bool(page.ocr_used),
            "ocr_confidence": getattr(page, "ocr_confidence", None),
            "needs_manual_review": bool(getattr(page, "needs_manual_review", False)),
        }
        for page in pages
    }
    return IngestedUploadPayload(
        blocks=blocks,
        page_count=len(pages),
        source_format=source_format,
        content_type="application/pdf",
        parser_version="pdf_ingest.v2",
        full_text=full_text,
        page_meta=page_meta,
    )


def _docx_payload(filename: str, file_bytes: bytes) -> IngestedUploadPayload:
    blocks = extract_docx_blocks(filename, file_bytes)
    full_text = "\n".join((block.content_text or "") for block in blocks if block.content_text)
    return IngestedUploadPayload(
        blocks=blocks,
        page_count=1,
        source_format="docx",
        content_type=_DOCX_MIME,
        parser_version="docx_ingest.v1",
        full_text=full_text,
        page_meta={1: {"source": "docx", "ocr_used": False}},
    )


def ingest_upload_bytes(
    filename: str,
    file_bytes: bytes,
    *,
    enable_ocr_fallback: bool = True,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> IngestedUploadPayload:
    normalized_ocr_provider = (ocr_provider or "").strip() or None
    if normalized_ocr_provider is not None:
        normalized_ocr_provider = normalize_ocr_provider(normalized_ocr_provider)

    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        return _pdf_payload(
            file_bytes,
            enable_ocr_fallback=enable_ocr_fallback,
            ocr_provider=normalized_ocr_provider,
            ocr_api_key=ocr_api_key,
            ocr_base_url=ocr_base_url,
            ocr_model=ocr_model,
        )
    if ext == ".docx":
        return _docx_payload(filename, file_bytes)
    if ext == ".doc":
        raise ValueError("暂不支持 .doc，请另存为 .docx 后上传")
    raise ValueError("unsupported file format, allowed: .pdf/.docx")


def ingest_upload_request(
    filename: str,
    file_bytes: bytes,
    *,
    enable_ocr_fallback: bool = True,
) -> IngestUploadResponse:
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        return ingest_pdf_bytes(filename=filename, pdf_bytes=file_bytes, enable_ocr_fallback=enable_ocr_fallback)
    if ext == ".docx":
        return ingest_docx_bytes(filename=filename, docx_bytes=file_bytes)
    if ext == ".doc":
        raise ValueError("暂不支持 .doc，请另存为 .docx 后上传")
    raise ValueError("unsupported file format, allowed: .pdf/.docx")
