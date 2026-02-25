from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.db.session import session_scope
from app.models.tables import (
    MethodologyReviewStatus,
    MethodologyRiskLevel,
    MethodologyRun,
    MethodologyRunStep,
    MethodologySnippet,
)


def _parse_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("invalid run_id") from exc


def create_methodology_run(
    *,
    source_type: str,
    source_note: str | None,
    input_kind: str,
    input_text: str | None,
    created_by: str,
) -> str:
    with session_scope() as db:
        row = MethodologyRun(
            status="RECEIVED",
            step=MethodologyRunStep.RECEIVED,
            progress=0,
            source_type=(source_type or "").strip() or "unknown",
            source_note=(source_note or "").strip() or None,
            input_kind=(input_kind or "text").strip() or "text",
            input_text=input_text,
            risk_level=MethodologyRiskLevel.MEDIUM,
            review_status=MethodologyReviewStatus.PENDING,
            created_by=(created_by or "system").strip() or "system",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return str(row.id)


def get_methodology_run(run_id: str) -> MethodologyRun | None:
    with session_scope() as db:
        return db.get(MethodologyRun, _parse_uuid(run_id))


def get_methodology_run_result(run_id: str) -> dict:
    run = get_methodology_run(run_id)
    if run is None:
        raise ValueError("run not found")

    payload: dict = {
        "run_id": run_id,
        "status": run.status,
        "step": run.step.value if hasattr(run.step, "value") else str(run.step),
        "progress": run.progress,
        "risk_level": run.risk_level.value if hasattr(run.risk_level, "value") else str(run.risk_level),
        "similarity_score": float(run.similarity_score or 0.0),
        "pii_removed": bool(run.pii_removed),
        "review_status": run.review_status.value if hasattr(run.review_status, "value") else str(run.review_status),
        "review_comment": run.review_comment,
        "reviewer": run.reviewer,
        "output": {},
    }

    if run.output_json_path:
        output_path = Path(run.output_json_path)
        if output_path.exists() and output_path.is_file():
            try:
                parsed = json.loads(output_path.read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    payload["output"] = parsed
            except json.JSONDecodeError:
                payload["output"] = {}
    return payload


def update_methodology_run(run_id: str, **values) -> None:  # noqa: ANN003
    with session_scope() as db:
        run = db.get(MethodologyRun, _parse_uuid(run_id))
        if run is None:
            raise ValueError("run not found")
        for key, value in values.items():
            setattr(run, key, value)
        run.updated_at = datetime.now(UTC)
        db.commit()


def review_methodology_run(*, run_id: str, status: str, comment: str | None, reviewer: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in {"approved", "rejected", "need_edit"}:
        raise ValueError("invalid review status")

    review_status = MethodologyReviewStatus(normalized)
    with session_scope() as db:
        run = db.get(MethodologyRun, _parse_uuid(run_id))
        if run is None:
            raise ValueError("run not found")

        run.review_status = review_status
        run.reviewer = (reviewer or "system").strip() or "system"
        run.review_comment = (comment or "").strip() or None
        run.reviewed_at = datetime.now(UTC)

        if review_status == MethodologyReviewStatus.APPROVED:
            run.status = "APPROVED"
            run.step = MethodologyRunStep.READY_FOR_REVIEW
        elif review_status == MethodologyReviewStatus.REJECTED:
            run.status = "REJECTED"
        else:
            run.status = "NEED_EDIT"
        db.commit()
        return review_status.value


def list_methodology_snippets(*, domain: str | None, tag: str | None, limit: int = 50) -> list[MethodologySnippet]:
    with session_scope() as db:
        stmt = select(MethodologySnippet).order_by(MethodologySnippet.created_at.desc()).limit(max(1, min(limit, 200)))
        if domain:
            stmt = stmt.where(MethodologySnippet.domain == domain)
        if tag:
            # StringListType is serialized text for sqlite; use LIKE fallback
            stmt = stmt.where(MethodologySnippet.tags.like(f"%{tag}%"))
        return list(db.execute(stmt).scalars().all())
