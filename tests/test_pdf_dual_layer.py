from __future__ import annotations

from app.services import pdf_ingest


def test_extract_pages_v2_triggers_ocr_when_text_too_short(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 200, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)

    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text="短文本", ocr_used=False)],
    )
    monkeypatch.setattr(pdf_ingest, "_ocr_page_with_fitz", lambda *_, **__: "OCR识别文本")

    pages = pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True)

    assert len(pages) == 1
    assert pages[0].ocr_used is True
    assert pages[0].source == "pypdf+ocr"
    assert pages[0].text == "OCR识别文本"


def test_extract_pages_v2_keeps_text_for_dual_layer_pdf(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 200, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)

    full_text = "这是双层PDF可提取文字。" * 20
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text=full_text, ocr_used=False)],
    )
    monkeypatch.setattr(
        pdf_ingest,
        "_ocr_page_with_fitz",
        lambda *_: (_ for _ in ()).throw(AssertionError("dual-layer page should not trigger OCR")),
    )

    pages = pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True)

    assert len(pages) == 1
    assert pages[0].ocr_used is False
    assert pages[0].source == "pypdf"
    assert pages[0].text == full_text


def test_extract_pages_v2_triggers_ocr_when_non_whitespace_ratio_too_low(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_textlen_threshold", 100, raising=False)
    monkeypatch.setattr(pdf_ingest.settings, "pdf_ocr_min_non_whitespace_ratio", 0.01, raising=False)

    sparse_text = "a" + (" " * 299)
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text=sparse_text, ocr_used=False)],
    )
    monkeypatch.setattr(pdf_ingest, "_ocr_page_with_fitz", lambda *_, **__: "OCR结果")

    pages = pdf_ingest.extract_pages_v2(b"%PDF-1.4", enable_ocr_fallback=True)

    assert len(pages) == 1
    assert pages[0].ocr_used is True
    assert pages[0].source == "pypdf+ocr"
    assert pages[0].text == "OCR结果"
