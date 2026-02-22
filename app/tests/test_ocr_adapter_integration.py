from __future__ import annotations

from app.services import pdf_ingest
from app.services.adapters import ocr as ocr_adapter


def test_create_ocr_adapter_selects_hunyuan() -> None:
    adapter = ocr_adapter.create_ocr_adapter("hunyuan")
    assert adapter.__class__.__name__ == "HunyuanOCRAdapter"


def test_create_ocr_adapter_selects_textin() -> None:
    adapter = ocr_adapter.create_ocr_adapter("textin")
    assert adapter.__class__.__name__ == "TextInOCRAdapter"


def test_professional_ocr_provider_path(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "ocr_provider", "hunyuan", raising=False)
    monkeypatch.setattr(pdf_ingest, "_render_page_png", lambda *_: b"fake-image")

    class _FakeAdapter:
        def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:
            assert image_bytes == b"fake-image"
            assert page_no == 1
            return "专业OCR文本"

    monkeypatch.setattr(pdf_ingest, "create_ocr_adapter", lambda *_args, **_kwargs: _FakeAdapter())
    text = pdf_ingest._ocr_page_with_configured_provider(b"%PDF", 1)
    assert text == "专业OCR文本"


def test_extract_pages_fallback_to_tesseract_when_professional_ocr_fails(monkeypatch) -> None:
    monkeypatch.setattr(pdf_ingest.settings, "ocr_provider", "docai", raising=False)
    monkeypatch.setattr(
        pdf_ingest,
        "_extract_with_pypdf",
        lambda _bytes: [pdf_ingest.PageExtract(page_no=1, text="", ocr_used=False)],
    )
    monkeypatch.setattr(
        pdf_ingest,
        "_ocr_page_with_configured_provider",
        lambda *_: (_ for _ in ()).throw(RuntimeError("provider down")),
    )
    monkeypatch.setattr(pdf_ingest, "_ocr_page_with_fitz", lambda *_: "tesseract文本")

    pages = pdf_ingest.extract_pages(b"%PDF-1.4", enable_ocr_fallback=True)
    assert pages[0].ocr_used is True
    assert pages[0].text == "tesseract文本"
