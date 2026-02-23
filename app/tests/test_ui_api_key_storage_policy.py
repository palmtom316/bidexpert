from __future__ import annotations

from pathlib import Path



def test_ui_api_key_uses_session_scope_not_local_storage() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    app_js = (repo_root / "app/ui/app.js").read_text(encoding="utf-8")

    assert 'localStorage.setItem("be_api_key"' not in app_js
    assert 'localStorage.removeItem("be_api_key"' not in app_js
    assert 'sessionStorage.setItem("be_api_key_session"' in app_js
    assert 'sessionStorage.removeItem("be_api_key_session"' in app_js
