import logging
from contextlib import asynccontextmanager
from time import perf_counter

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.api.endpoints.stats import router as stats_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.init_db import init_db
from app.observability import CONTENT_TYPE_LATEST, record_http_request, render_metrics
from app.services.api_rate_limiter import allow_api_request

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        init_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database init skipped: %s", exc)
    yield


app = FastAPI(title="BidExpert API", version="1.0.0", lifespan=lifespan)


def _should_apply_rate_limit(path: str) -> bool:
    return (
        path == "/health"
        or path.startswith("/v1/")
        or path.startswith("/api/")
        or path.startswith("/stats/")
    )


def _client_identifier(request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        first = xff.split(",", maxsplit=1)[0].strip()
        if first:
            return first
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


@app.middleware("http")
async def api_rate_limit_middleware(request, call_next):  # type: ignore[no-untyped-def]
    started_at = perf_counter()
    response = None
    try:
        if settings.api_rate_limit_enabled and _should_apply_rate_limit(request.url.path):
            allowed, retry_after = allow_api_request(
                identifier=_client_identifier(request),
                limit=settings.api_rate_limit_requests,
                window_seconds=settings.api_rate_limit_window_seconds,
            )
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "rate limit exceeded"},
                    headers={"Retry-After": str(max(1, retry_after))},
                )
                return response
        response = await call_next(request)
        return response
    finally:
        if settings.metrics_enabled:
            status_code = response.status_code if response is not None else 500
            record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=int(status_code),
                duration_seconds=perf_counter() - started_at,
            )

_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(stats_router, prefix="/stats", tags=["stats"])
if settings.serve_ui_static:
    app.mount("/ui", StaticFiles(directory="app/ui", html=True), name="ui")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/ui")


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="metrics disabled")
    return Response(content=render_metrics(), media_type=CONTENT_TYPE_LATEST)
