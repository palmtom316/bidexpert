from __future__ import annotations

import pytest

from app.services import pdf_ingest


def test_extract_pages_v2_allows_ocr_provider_override_to_tesseract(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "ocr_provider", "glm-ocr", raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 200, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text="", ocr_used=False)],
    )

    monkeypatch.setattr(pdf_ingest, "_ocr_page_with_fitz", lambda *_args, **_kwargs: "本地OCR文本")
    monkeypatch.setattr(
        pdf_ingest,
        "_ocr_page_with_configured_provider",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not call remote adapter")),
    )

    pages = pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True, ocr_provider="tesseract")

    assert len(pages) == 1
    assert pages[0].ocr_used is True
    assert pages[0].text == "本地OCR文本"
    assert pages[0].source == "pypdf+ocr:tesseract"


def test_extract_pages_v2_allows_ocr_provider_override_to_remote_adapter(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "ocr_provider", "tesseract", raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 200, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text="", ocr_used=False)],
    )
    monkeypatch.setattr(
        pdf_ingest,
        "_ocr_page_with_fitz",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not call local OCR")),
    )

    captured: dict[str, str | None] = {}

    def _fake_remote(_pdf: bytes, page_no: int, dpi: int | None = None, ocr_provider: str | None = None) -> str:
        assert page_no == 1
        captured["provider"] = ocr_provider
        return "远程OCR文本"

    monkeypatch.setattr(pdf_ingest, "_ocr_page_with_configured_provider", _fake_remote)

    pages = pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True, ocr_provider="docai")

    assert len(pages) == 1
    assert pages[0].ocr_used is True
    assert pages[0].text == "远程OCR文本"
    assert pages[0].source == "pypdf+ocr:docai"
    assert captured["provider"] == "docai"


def test_extract_pages_v2_rejects_unknown_ocr_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text="", ocr_used=False)],
    )
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 200, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)

    with pytest.raises(ValueError, match="unsupported ocr provider"):
        pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True, ocr_provider="unsupported-x")
