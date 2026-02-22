from __future__ import annotations

from time import perf_counter

from celery import Celery
from celery.signals import task_postrun, task_prerun, task_retry

from app.core.config import settings
from app.core.logging import configure_logging
from app.observability import record_task_duration, record_task_event

configure_logging()

celery_app = Celery(
    "bidexpert",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.worker.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
)


_TASK_STARTED_AT: dict[str, float] = {}


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **kwargs) -> None:  # noqa: ANN001
    del kwargs
    if task_id:
        _TASK_STARTED_AT[str(task_id)] = perf_counter()
    task_name = getattr(task, "name", "unknown")
    record_task_event(task_name=str(task_name), status="started")


@task_retry.connect
def _on_task_retry(request=None, reason=None, einfo=None, **kwargs) -> None:  # noqa: ANN001
    del reason, einfo, kwargs
    task_name = getattr(request, "task", "unknown")
    record_task_event(task_name=str(task_name), status="retry")


@task_postrun.connect
def _on_task_postrun(task_id=None, task=None, state=None, **kwargs) -> None:  # noqa: ANN001
    del kwargs
    task_name = getattr(task, "name", "unknown")
    normalized_state = str(state or "").upper()
    status = None
    if normalized_state == "SUCCESS":
        status = "succeeded"
    elif normalized_state in {"FAILURE", "REVOKED"}:
        status = "failed"

    if status is not None:
        record_task_event(task_name=str(task_name), status=status)
        started_at = _TASK_STARTED_AT.get(str(task_id)) if task_id else None
        if started_at is not None:
            record_task_duration(
                task_name=str(task_name),
                duration_seconds=perf_counter() - started_at,
                status=status,
            )

    if task_id and normalized_state != "RETRY":
        _TASK_STARTED_AT.pop(str(task_id), None)
