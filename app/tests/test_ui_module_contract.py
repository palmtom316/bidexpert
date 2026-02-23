from __future__ import annotations

from pathlib import Path



def test_ui_modules_and_entry_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    state_module = repo_root / "app/ui/modules/state.js"
    validation_module = repo_root / "app/ui/modules/validation.js"
    app_js = (repo_root / "app/ui/app.js").read_text(encoding="utf-8")
    index_html = (repo_root / "app/ui/index.html").read_text(encoding="utf-8")

    assert state_module.exists(), "expected app/ui/modules/state.js"
    assert validation_module.exists(), "expected app/ui/modules/validation.js"
    assert 'from "./modules/state.js"' in app_js
    assert 'from "./modules/validation.js"' in app_js
    assert 'script type="module"' in index_html and '/ui/app.js' in index_html
