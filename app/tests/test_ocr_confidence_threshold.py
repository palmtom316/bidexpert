from __future__ import annotations

from types import SimpleNamespace

from app.services.ingest import file_router



def test_pdf_payload_marks_low_confidence_ocr_for_manual_review(monkeypatch) -> None:
    monkeypatch.setattr(
        file_router,
        "extract_pages_v2",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                page_no=1,
                text="OCR text",
                ocr_used=True,
                source="pypdf+ocr:docai",
                ocr_confidence=0.41,
                needs_manual_review=True,
            )
        ],
    )

    payload = file_router.ingest_upload_bytes(
        filename="demo.pdf",
        file_bytes=b"%PDF-1.4",
        enable_ocr_fallback=True,
        ocr_provider="docai",
    )

    page_meta = payload.page_meta[1]
    assert page_meta["ocr_used"] is True
    assert page_meta["ocr_confidence"] == 0.41
    assert page_meta["needs_manual_review"] is True
