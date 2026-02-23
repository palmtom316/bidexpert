from __future__ import annotations

from pathlib import Path



def test_ui_validation_rules_and_field_error_targets_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    validation_js = (repo_root / "app/ui/modules/validation.js").read_text(encoding="utf-8")
    app_js = (repo_root / "app/ui/app.js").read_text(encoding="utf-8")
    index_html = (repo_root / "app/ui/index.html").read_text(encoding="utf-8")

    assert "validateExpertUploadForm" in validation_js
    assert "validateStructuredIngestForm" in validation_js
    assert "setFieldError" in validation_js
    assert "clearFieldError" in validation_js

    assert "validateExpertUploadForm" in app_js
    assert "validateStructuredIngestForm" in app_js
    assert "setFieldError(" in app_js

    for marker in (
        "expertPdfFilesError",
        "structuredFormError",
        "ocrApiKeyError",
        "ocrModelError",
        "ocrBaseUrlError",
    ):
        assert marker in index_html
