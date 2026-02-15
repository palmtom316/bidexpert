from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.tables import CompletedBid

_ALLOWED_BID_RESULTS = {"WON", "LOST"}


def _normalize_uuid(value: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise ValueError(f"invalid {field_name}") from exc


def _normalize_optional_project_id(project_id: str | None) -> str | None:
    raw = (project_id or "").strip()
    if not raw:
        return None
    return _normalize_uuid(raw, "project_id")


def _normalize_bid_result(bid_result: str | None) -> str:
    normalized = (bid_result or "WON").strip().upper()
    if normalized not in _ALLOWED_BID_RESULTS:
        raise ValueError("bid_result must be WON|LOST")
    return normalized


def _parse_completed_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError("completed_date must be YYYY-MM-DD") from exc


def create_completed_bid(
    *,
    project_id: str | None,
    project_name: str,
    engineering_category: str | None,
    tenderer: str | None,
    bid_result: str,
    file_name: str,
    file_info: str | None,
    completed_date: str | None,
    created_by: str | None = "system",
) -> CompletedBid:
    project_name_clean = project_name.strip()
    file_name_clean = file_name.strip()
    if not project_name_clean:
        raise ValueError("project_name is required")
    if not file_name_clean:
        raise ValueError("file_name is required")

    record = CompletedBid(
        project_id=_normalize_optional_project_id(project_id),
        project_name=project_name_clean,
        engineering_category=(engineering_category or "").strip() or None,
        tenderer=(tenderer or "").strip() or None,
        bid_result=_normalize_bid_result(bid_result),
        file_name=file_name_clean,
        file_info=(file_info or "").strip() or None,
        completed_date=_parse_completed_date(completed_date),
        created_by=(created_by or "").strip() or "system",
        updated_at=datetime.now(UTC),
    )

    try:
        with SessionLocal() as db:
            db.add(record)
            db.commit()
            db.refresh(record)
            return record
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist completed bid record: {exc}") from exc


def list_completed_bids(*, project_id: str | None = None, limit: int = 200) -> list[CompletedBid]:
    project_id_norm = _normalize_optional_project_id(project_id)
    safe_limit = max(1, min(int(limit), 500))
    try:
        with SessionLocal() as db:
            stmt = select(CompletedBid).order_by(CompletedBid.created_at.desc()).limit(safe_limit)
            if project_id_norm:
                stmt = stmt.where(CompletedBid.project_id == project_id_norm)
            return list(db.execute(stmt).scalars().all())
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to query completed bid records: {exc}") from exc


def delete_completed_bid(record_id: str) -> bool:
    try:
        record_uuid = uuid.UUID(record_id)
        with SessionLocal() as db:
            record = db.execute(select(CompletedBid).where(CompletedBid.id == record_uuid)).scalar_one_or_none()
            if not record:
                return False
            db.delete(record)
            db.commit()
            return True
    except ValueError as exc:
        raise ValueError("invalid record_id") from exc
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to delete completed bid record: {exc}") from exc
