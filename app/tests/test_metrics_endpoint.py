from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import routes
from app.api.endpoints import stats as stats_endpoint
from app.main import app
from app.observability.metrics import HTTP_REQUESTS_TOTAL, record_task_duration, record_task_event


def test_metrics_endpoint_exposes_prometheus(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_public_enabled", True, raising=False)
    client = TestClient(app)
    client.get("/health", headers={"X-Forwarded-For": "198.51.100.99"})

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    assert "bidexpert_http_requests_total" in response.text


def test_metrics_endpoint_requires_auth_when_public_disabled(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_public_enabled", False, raising=False)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "metrics-secret", raising=False)

    client = TestClient(app)
    unauthorized = client.get("/metrics")
    assert unauthorized.status_code == 401

    authorized = client.get("/metrics", headers={"X-API-Key": "metrics-secret"})
    assert authorized.status_code == 200


def test_metrics_uses_route_template_for_path_labels(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_public_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_enabled", False, raising=False)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "metrics-secret", raising=False)
    monkeypatch.setattr(
        routes,
        "get_task_result",
        lambda task_id: {"task_id": task_id, "status": "PENDING", "result": None},
    )
    client = TestClient(app)

    label = HTTP_REQUESTS_TOTAL.labels(method="GET", path="/v1/tasks/{task_id}", status_code="200")
    before = float(label._value.get())  # type: ignore[attr-defined]

    headers = {"X-API-Key": "metrics-secret"}
    assert client.get("/v1/tasks/task-a", headers=headers).status_code == 200
    assert client.get("/v1/tasks/task-b", headers=headers).status_code == 200

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


def test_metrics_export_includes_429_and_5xx_counters(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_public_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_enabled", True, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_requests", 1, raising=False)
    monkeypatch.setattr(settings, "api_rate_limit_window_seconds", 60, raising=False)
    monkeypatch.setattr(routes.settings, "auth_mode", "api_key", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", "metrics-secret", raising=False)
    monkeypatch.setattr(
        routes,
        "get_task_result",
        lambda task_id: {"task_id": task_id, "status": "PENDING", "result": None},
    )

    headers = {"X-API-Key": "metrics-secret", "X-Forwarded-For": "203.0.113.8"}
    client = TestClient(app)
    assert client.get("/v1/tasks/task-1", headers=headers).status_code == 200
    assert client.get("/v1/tasks/task-2", headers=headers).status_code == 429

    monkeypatch.setattr(settings, "api_rate_limit_enabled", False, raising=False)
    monkeypatch.setattr(
        routes,
        "get_task_result",
        lambda _task_id: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    error_client = TestClient(app, raise_server_exceptions=False)
    assert error_client.get("/v1/tasks/task-3", headers={"X-API-Key": "metrics-secret"}).status_code == 500

    metrics_text = client.get("/metrics").text
    assert "bidexpert_http_rate_limit_total" in metrics_text
    assert "bidexpert_http_server_errors_total" in metrics_text


def test_metrics_export_includes_celery_task_event_counters(monkeypatch) -> None:
    from app.main import settings

    monkeypatch.setattr(settings, "metrics_enabled", True, raising=False)
    monkeypatch.setattr(settings, "metrics_public_enabled", True, raising=False)
    record_task_event(task_name="tasks.section_pipeline", status="started")
    record_task_event(task_name="tasks.section_pipeline", status="failed")
    record_task_duration(task_name="tasks.section_pipeline", duration_seconds=0.25, status="failed")

    client = TestClient(app)
    text = client.get("/metrics").text
    assert "bidexpert_celery_task_events_total" in text
    assert "bidexpert_celery_task_duration_seconds" in text
