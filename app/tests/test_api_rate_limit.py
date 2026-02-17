from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.api_rate_limiter import reset_local_rate_limit_state



def test_api_rate_limit_blocks_excess_requests(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "api_rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_requests", 2, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60, raising=False)

    reset_local_rate_limit_state()
    client = TestClient(app)
    headers = {"X-Forwarded-For": "198.51.100.10"}

    assert client.get("/health", headers=headers).status_code == 200
    assert client.get("/health", headers=headers).status_code == 200

    blocked = client.get("/health", headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After")



def test_api_rate_limit_isolated_by_client_ip(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "api_rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60, raising=False)

    reset_local_rate_limit_state()
    client = TestClient(app)

    assert client.get("/health", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 200
    assert client.get("/health", headers={"X-Forwarded-For": "203.0.113.2"}).status_code == 200
    assert client.get("/health", headers={"X-Forwarded-For": "203.0.113.1"}).status_code == 429
