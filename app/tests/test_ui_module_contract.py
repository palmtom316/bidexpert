"""Task 12: 前端模块化与状态治理 — contract tests.

Covers:
- R13: Frontend app.js is split into modules with centralized state
- Verifies module files exist, state.js exports state shape, validation.js exists
"""
from __future__ import annotations

import pathlib
import re

UI_DIR = pathlib.Path(__file__).resolve().parent.parent / "ui"
MODULES_DIR = UI_DIR / "modules"


# ---------------------------------------------------------------------------
# R13-1: Module directory and key files exist
# ---------------------------------------------------------------------------

def test_modules_directory_exists() -> None:
    assert MODULES_DIR.is_dir(), f"Expected {MODULES_DIR} to be a directory"


def test_state_module_exists() -> None:
    assert (MODULES_DIR / "state.js").is_file()


def test_validation_module_exists() -> None:
    assert (MODULES_DIR / "validation.js").is_file()


# ---------------------------------------------------------------------------
# R13-2: state.js defines centralized state object
# ---------------------------------------------------------------------------

def test_state_js_exports_state_object() -> None:
    content = (MODULES_DIR / "state.js").read_text(encoding="utf-8")
    assert "const state" in content or "window.AppState" in content


def test_state_js_has_core_fields() -> None:
    content = (MODULES_DIR / "state.js").read_text(encoding="utf-8")
    for field in ["projectId", "outlineId", "sections", "apiKey"]:
        assert field in content, f"state.js missing core field: {field}"


# ---------------------------------------------------------------------------
# R13-3: Module files exist for major UI sections
# ---------------------------------------------------------------------------

EXPECTED_MODULES = [
    "expert_hub.js",
    "tender_hub.js",
    "bid_workbench.js",
    "review.js",
    "publish.js",
]


def test_major_module_files_exist() -> None:
    missing = [m for m in EXPECTED_MODULES if not (MODULES_DIR / m).is_file()]
    assert not missing, f"Missing module files: {missing}"


# ---------------------------------------------------------------------------
# R13-4: index.html uses a single entry script to avoid duplicate globals
# ---------------------------------------------------------------------------

def test_index_html_uses_single_entry_script() -> None:
    html = (UI_DIR / "index.html").read_text(encoding="utf-8")
    assert "/ui/app.js" in html, "index.html should load app.js entrypoint"
    assert "modules/state.js" not in html, "index.html should not load module scripts together with app.js"


# ---------------------------------------------------------------------------
# R13-5: Each module file defines its init function
# ---------------------------------------------------------------------------

def test_each_module_has_init() -> None:
    for mod_name in EXPECTED_MODULES:
        content = (MODULES_DIR / mod_name).read_text(encoding="utf-8")
        assert re.search(r"init\s*[\(({]", content), f"{mod_name} missing init function"


# ---------------------------------------------------------------------------
# R13-6: validation.js has validation helpers
# ---------------------------------------------------------------------------

def test_validation_js_has_validate_functions() -> None:
    content = (MODULES_DIR / "validation.js").read_text(encoding="utf-8")
    assert "validate" in content.lower(), "validation.js should contain validation functions"
