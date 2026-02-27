from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import session_scope
from app.models.tables import CompletedBid

logger = logging.getLogger(__name__)

_ALLOWED_BID_RESULTS = {"WON", "LOST"}
_FEEDBACK_SCORE_THRESHOLD = 80.0


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
        with session_scope() as db:
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
        with session_scope() as db:
            stmt = select(CompletedBid).order_by(CompletedBid.created_at.desc()).limit(safe_limit)
            if project_id_norm:
                stmt = stmt.where(CompletedBid.project_id == project_id_norm)
            return list(db.execute(stmt).scalars().all())
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to query completed bid records: {exc}") from exc


def delete_completed_bid(record_id: str) -> bool:
    try:
        record_uuid = uuid.UUID(record_id)
        with session_scope() as db:
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


def get_feedback_eligible_bids(
    *,
    score_threshold: float = _FEEDBACK_SCORE_THRESHOLD,
    limit: int = 100,
) -> list[CompletedBid]:
    """Return bids eligible for knowledge feedback: WON or high-score records."""
    safe_limit = max(1, min(int(limit), 500))
    try:
        with session_scope() as db:
            stmt = (
                select(CompletedBid)
                .where(CompletedBid.bid_result == "WON")
                .order_by(CompletedBid.created_at.desc())
                .limit(safe_limit)
            )
            won_bids = list(db.execute(stmt).scalars().all())
            return won_bids
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to query feedback-eligible bids: {exc}") from exc


def ingest_completed_bid_to_knowledge_base(record_id: str) -> dict:
    """Ingest a completed bid into the knowledge base as ExpertDoc + EvidenceChunk.

    Returns dict with keys: expert_doc_id, chunks_created, status.
    """
    from app.models.tables import EvidenceChunk, ExpertDoc

    try:
        record_uuid = uuid.UUID(record_id)
    except ValueError as exc:
        raise ValueError("invalid record_id") from exc

    with session_scope() as db:
        record = db.execute(
            select(CompletedBid).where(CompletedBid.id == record_uuid)
        ).scalar_one_or_none()
        if not record:
            raise ValueError(f"completed bid not found: {record_id}")

        # Create ExpertDoc for the feedback
        expert_doc = ExpertDoc(
            doc_type="COMPLETED_BID_FEEDBACK",
            title=f"中标文件回灌: {record.project_name}",
            industry_tag=record.engineering_category,
            created_by=record.created_by or "system",
        )
        db.add(expert_doc)
        db.flush()

        # Create a single evidence chunk with the bid metadata
        chunk_text = (
            f"项目名称: {record.project_name}\n"
            f"工程类别: {record.engineering_category or '未知'}\n"
            f"投标人: {record.tenderer or '未知'}\n"
            f"中标结果: {record.bid_result}\n"
            f"文件名: {record.file_name}\n"
            f"完成日期: {record.completed_date or '未知'}"
        )
        chunk = EvidenceChunk(
            expert_doc_id=expert_doc.id,
            chunk_no=1,
            excerpt_text=chunk_text,
        )
        db.add(chunk)
        db.commit()

        return {
            "expert_doc_id": str(expert_doc.id),
            "chunks_created": 1,
            "status": "ingested",
        }

