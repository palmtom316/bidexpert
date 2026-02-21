from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.contracts import DocBlockItem, IngestUploadResponse
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


def _pdf_payload(file_bytes: bytes, enable_ocr_fallback: bool) -> IngestedUploadPayload:
    pages: list[PageExtract] = extract_pages_v2(file_bytes, enable_ocr_fallback=enable_ocr_fallback)
    blocks = build_doc_blocks(pages)
    full_text = "\f".join(page.text for page in pages)
    source_format = "scanned_pdf" if any(page.ocr_used for page in pages) else "pdf"
    page_meta = {
        int(page.page_no): {
            "source": page.source or ("pypdf+ocr" if page.ocr_used else "pypdf"),
            "ocr_used": bool(page.ocr_used),
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
) -> IngestedUploadPayload:
    ext = Path(filename or "").suffix.lower()
    if ext == ".pdf":
        return _pdf_payload(file_bytes, enable_ocr_fallback=enable_ocr_fallback)
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
