"""Celery task wrappers for tender v1.1 pipeline."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

_TRANSIENT_ERRORS = (RuntimeError, OSError, ConnectionError, TimeoutError)


@celery_app.task(
    bind=True,
    name="tasks.tender_import_pipeline",
    max_retries=settings.task_max_retries,
    autoretry_for=_TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=120,
    retry_jitter=True,
)
def tender_import_pipeline_task(self, run_id: str) -> dict:  # type: ignore[no-untyped-def]
    """Execute the full 12-step tender import pipeline for a given run."""
    self.update_state(state="PROGRESS", meta={"stage": "PIPELINE_START"})
    try:
        from app.tender.pipeline import run_pipeline

        result = run_pipeline(run_id)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("tender import pipeline failed for run_id=%s", run_id)
        # Update run status to FAILED
        try:
            from app.db.session import session_scope
            from app.models.tables import TenderImportRun, TenderRunStep
            import uuid

            with session_scope() as db:
                run = db.get(TenderImportRun, uuid.UUID(run_id))
                if run and run.current_step not in (TenderRunStep.FATAL_BLOCKED,):
                    run.current_step = TenderRunStep.FAILED
                    run.error_detail = str(exc)[:2000]
                    db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("failed to mark run as FAILED")
        raise
