from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_exposes_prometheus(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    client = TestClient(app)
    client.get("/health", headers={"X-Forwarded-For": "198.51.100.99"})

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "bidexpert_http_requests_total" in response.text
