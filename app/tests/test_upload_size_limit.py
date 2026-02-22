from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app


def test_upload_is_rejected_when_exceeding_configured_limit(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes.settings, "max_upload_bytes", 10, raising=False)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "test-key", raising=False)
    client = TestClient(app)

    response = client.post(
        "/v1/tender/ingest-upload",
        files={"file": ("oversize.pdf", BytesIO(b"%PDF-1.4-TOO-LARGE"), "application/pdf")},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 413
    assert "max_upload_bytes" in response.json()["detail"]
