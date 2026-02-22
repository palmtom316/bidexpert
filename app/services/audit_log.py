from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import session_scope
from app.models.tables import AuditLog

logger = logging.getLogger(__name__)


def _parse_optional_uuid(value: str | None) -> uuid.UUID | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise ValueError("invalid project_id") from exc


def record_audit_event(
    *,
    action: str,
    actor_user_id: str,
    project_id: str | None = None,
    target_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    action_value = (action or "").strip()
    if not action_value:
        raise ValueError("action is required")

    try:
        with session_scope() as db:
            db.add(
                AuditLog(
                    project_id=_parse_optional_uuid(project_id),
                    actor_user_id=(actor_user_id or "").strip() or "system",
                    action=action_value,
                    target_id=(target_id or "").strip() or None,
                    metadata_json=dict(metadata or {}),
                )
            )
            db.commit()
    except (SQLAlchemyError, ValueError):
        logger.warning("audit log persistence failed for action=%s", action_value, exc_info=True)


def list_audit_logs(
    *,
    project_id: str | None = None,
    action: str | None = None,
    limit: int = 100,
) -> list[AuditLog]:
    safe_limit = max(1, min(int(limit), 500))
    project_uuid = _parse_optional_uuid(project_id)
    normalized_action = (action or "").strip()

    try:
        with session_scope() as db:
            stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(safe_limit)
            if project_uuid is not None:
                stmt = stmt.where(AuditLog.project_id == project_uuid)
            if normalized_action:
                stmt = stmt.where(AuditLog.action == normalized_action)
            return list(db.execute(stmt).scalars().all())
    except SQLAlchemyError as exc:
        raise RuntimeError("failed to query audit logs") from exc
