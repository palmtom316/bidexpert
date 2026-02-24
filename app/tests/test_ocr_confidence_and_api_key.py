"""Task 14: API Key 存储安全与 OCR 置信度 — tests.

Covers:
- R15: API Key should use sessionStorage, not localStorage for persistence
- R16: OCR adapter returns confidence; config has ocr_confidence_threshold
"""
from __future__ import annotations

import pathlib

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"


# ---------------------------------------------------------------------------
# R15: API Key storage — no localStorage for sensitive keys
# ---------------------------------------------------------------------------

def test_api_key_not_persisted_to_localstorage() -> None:
    """app.js should use sessionStorage (not localStorage) for be_api_key."""
    content = (UI_DIR / "app.js").read_text(encoding="utf-8")
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        if "localStorage.setItem" in line and "api_key" in line.lower():
            assert False, (
                f"Line {i}: API key still written to localStorage. "
                "Use sessionStorage instead."
            )


def test_ocr_api_key_not_persisted_to_localstorage() -> None:
    """OCR API key should use sessionStorage, not localStorage."""
    content = (UI_DIR / "app.js").read_text(encoding="utf-8")
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        if "localStorage.setItem" in line and "OCR_API_KEY" in line:
            assert False, (
                f"Line {i}: OCR API key still written to localStorage. "
                "Use sessionStorage instead."
            )


# ---------------------------------------------------------------------------
# R16: OCR confidence threshold
# ---------------------------------------------------------------------------

def test_config_has_ocr_confidence_threshold() -> None:
    from app.core.config import settings
    assert hasattr(settings, "ocr_confidence_threshold")


def test_ocr_confidence_threshold_default() -> None:
    from app.core.config import settings
    assert 0.0 < settings.ocr_confidence_threshold <= 1.0


def test_ocr_result_dataclass_has_confidence() -> None:
    from app.services.adapters.ocr import OCRPageResult
    result = OCRPageResult(page_no=1, text="test", confidence=0.95)
    assert result.confidence == 0.95


def test_ocr_result_low_confidence_flagged() -> None:
    from app.services.adapters.ocr import OCRPageResult
    from app.core.config import settings
    result = OCRPageResult(page_no=1, text="test", confidence=0.3)
    assert result.confidence < settings.ocr_confidence_threshold
