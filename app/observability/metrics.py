from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS_TOTAL = Counter(
    "bidexpert_http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "bidexpert_http_request_duration_seconds",
    "HTTP request duration seconds",
    ["method", "path"],
)
HTTP_RATE_LIMIT_TOTAL = Counter(
    "bidexpert_http_rate_limit_total",
    "Total number of HTTP 429 responses",
    ["method", "path"],
)
HTTP_SERVER_ERRORS_TOTAL = Counter(
    "bidexpert_http_server_errors_total",
    "Total number of HTTP 5xx responses",
    ["method", "path", "status_code"],
)
CELERY_TASK_EVENTS_TOTAL = Counter(
    "bidexpert_celery_task_events_total",
    "Total number of celery task lifecycle events",
    ["task_name", "status"],
)
CELERY_TASK_DURATION_SECONDS = Histogram(
    "bidexpert_celery_task_duration_seconds",
    "Celery task duration seconds",
    ["task_name", "status"],
)


def record_http_request(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(max(duration_seconds, 0.0))
    if int(status_code) == 429:
        HTTP_RATE_LIMIT_TOTAL.labels(method=method, path=path).inc()
    if int(status_code) >= 500:
        HTTP_SERVER_ERRORS_TOTAL.labels(
            method=method,
            path=path,
            status_code=str(status_code),
        ).inc()


def _normalize_task_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized in {"started", "succeeded", "failed", "retry"}:
        return normalized
    return "unknown"


def record_task_event(*, task_name: str, status: str) -> None:
    CELERY_TASK_EVENTS_TOTAL.labels(
        task_name=(task_name or "unknown"),
        status=_normalize_task_status(status),
    ).inc()


def record_task_duration(*, task_name: str, duration_seconds: float, status: str) -> None:
    CELERY_TASK_DURATION_SECONDS.labels(
        task_name=(task_name or "unknown"),
        status=_normalize_task_status(status),
    ).observe(max(float(duration_seconds), 0.0))


def render_metrics() -> bytes:
    return generate_latest()


__all__ = [
    "CONTENT_TYPE_LATEST",
    "record_http_request",
    "record_task_event",
    "record_task_duration",
    "render_metrics",
]
