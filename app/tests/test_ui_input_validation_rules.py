"""Task 13: 前端输入前置校验 — contract tests.

Covers:
- R14: Client-side validation rules exist for key input fields
- validation.js has required, uuid, minLength, maxLength, fileRequired validators
"""
from __future__ import annotations

import pathlib
import re

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"
MODULES_DIR = UI_DIR / "modules"


# ---------------------------------------------------------------------------
# R14-1: validation.js has core validator functions
# ---------------------------------------------------------------------------

def _read_validation_js() -> str:
    return (MODULES_DIR / "validation.js").read_text(encoding="utf-8")


def test_validation_has_required_rule() -> None:
    content = _read_validation_js()
    assert "required" in content


def test_validation_has_uuid_rule() -> None:
    content = _read_validation_js()
    assert "uuid" in content.lower()


def test_validation_has_min_length_rule() -> None:
    content = _read_validation_js()
    assert "minLength" in content or "min_length" in content


def test_validation_has_max_length_rule() -> None:
    content = _read_validation_js()
    assert "maxLength" in content or "max_length" in content


def test_validation_has_file_required_rule() -> None:
    content = _read_validation_js()
    assert "fileRequired" in content or "file_required" in content or "fileInput" in content


# ---------------------------------------------------------------------------
# R14-2: validation.js has a validate orchestrator
# ---------------------------------------------------------------------------

def test_validation_has_validate_function() -> None:
    content = _read_validation_js()
    assert re.search(r"validate\s*\(", content)


def test_validation_has_error_display() -> None:
    content = _read_validation_js()
    assert "showFieldErrors" in content or "showErrors" in content or "Toast" in content


# ---------------------------------------------------------------------------
# R14-3: validation.js returns structured errors
# ---------------------------------------------------------------------------

def test_validation_returns_field_and_message() -> None:
    content = _read_validation_js()
    assert "field" in content and "message" in content
