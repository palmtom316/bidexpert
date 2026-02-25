from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import HTTPException

from app.schemas.contracts import (
    MethodologyExtractRequest,
    MethodologyExtractResponse,
    MethodologyPublishResponse,
    MethodologyReviewRequest,
    MethodologyReviewResponse,
    MethodologyRunResponse,
)


def _iso(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def methodology_extract_handler(
    payload: MethodologyExtractRequest,
    *,
    create_methodology_extract_run_fn: Callable[..., str],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> MethodologyExtractResponse:
    try:
        run_id = create_methodology_extract_run_fn(
            text=payload.text,
            source_type=payload.source_type,
            source_note=payload.source_note or payload.note,
            domain=payload.domain,
            tags=payload.tags,
            created_by=resolved_created_by_fn(None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc

    return MethodologyExtractResponse(run_id=run_id, status="RECEIVED")


def methodology_run_handler(
    run_id: str,
    *,
    get_methodology_run_fn: Callable[[str], object | None],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> MethodologyRunResponse:
    try:
        run = get_methodology_run_fn(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc

    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    return MethodologyRunResponse(
        run_id=run_id,
        status=str(run.status),
        step=run.step.value if hasattr(run.step, "value") else str(run.step),
        progress=int(run.progress or 0),
        source_type=str(run.source_type),
        source_note=run.source_note,
        risk_level=run.risk_level.value if hasattr(run.risk_level, "value") else str(run.risk_level),
        similarity_score=float(run.similarity_score or 0.0),
        pii_removed=bool(run.pii_removed),
        review_status=run.review_status.value if hasattr(run.review_status, "value") else str(run.review_status),
        reviewer=run.reviewer,
        review_comment=run.review_comment,
        created_at=_iso(run.created_at),
        updated_at=_iso(run.updated_at),
    )


def methodology_review_handler(
    run_id: str,
    payload: MethodologyReviewRequest,
    *,
    review_methodology_run_fn: Callable[..., str],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> MethodologyReviewResponse:
    try:
        status = review_methodology_run_fn(
            run_id=run_id,
            status=payload.status,
            comment=payload.comment,
            reviewer=resolved_created_by_fn(None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc

    return MethodologyReviewResponse(run_id=run_id, status=status)


def methodology_publish_handler(
    run_id: str,
    *,
    publish_methodology_run_fn: Callable[..., str],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> MethodologyPublishResponse:
    try:
        snippet_id = publish_methodology_run_fn(run_id=run_id, actor=resolved_created_by_fn(None))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc

    return MethodologyPublishResponse(run_id=run_id, snippet_id=snippet_id, status="PUBLISHED")
