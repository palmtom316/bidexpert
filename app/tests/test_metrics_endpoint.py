from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes
from app.api.endpoints import stats as stats_endpoint
from app.main import app
from app.observability.metrics import HTTP_REQUESTS_TOTAL


def test_metrics_endpoint_exposes_prometheus(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    client = TestClient(app)
    client.get("/health", headers={"X-Forwarded-For": "198.51.100.99"})

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "bidexpert_http_requests_total" in response.text


def test_metrics_uses_route_template_for_path_labels(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_enabled", False, raising=False)
    monkeypatch.setattr(
        routes,
        "get_task_result",
        lambda task_id: {"task_id": task_id, "status": "PENDING", "result": None},
    )
    client = TestClient(app)

    label = HTTP_REQUESTS_TOTAL.labels(method="GET", path="/v1/tasks/{task_id}", status_code="200")
    before = float(label._value.get())  # type: ignore[attr-defined]

    assert client.get("/v1/tasks/task-a").status_code == 200
    assert client.get("/v1/tasks/task-b").status_code == 200

    after = float(label._value.get())  # type: ignore[attr-defined]
    assert after >= before + 2


def test_stats_endpoint_requires_same_auth_dependency(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "stats-secret", raising=False)
    monkeypatch.setattr(routes.settings, "api_rate_limit_enabled", False, raising=False)

    class _DummyRows:
        def all(self) -> list[object]:
            return []

    class _DummySession:
        def execute(self, stmt):  # noqa: ANN001, ANN201
            return _DummyRows()

    app.dependency_overrides[stats_endpoint.get_db] = lambda: _DummySession()

    client = TestClient(app)
    unauthorized = client.get("/stats/usage")
    assert unauthorized.status_code == 401

    authorized = client.get("/stats/usage", headers={"X-API-Key": "stats-secret"})
    assert authorized.status_code == 200
    app.dependency_overrides.clear()
