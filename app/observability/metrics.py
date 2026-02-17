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


def record_http_request(*, method: str, path: str, status_code: int, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(max(duration_seconds, 0.0))


def render_metrics() -> bytes:
    return generate_latest()


__all__ = ["CONTENT_TYPE_LATEST", "record_http_request", "render_metrics"]

