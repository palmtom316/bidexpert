from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.tables import LLMCallLog, Project
from app.services.governance import reserve_budget


def _try_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _uuid_list(values: list[str]) -> list[uuid.UUID]:
    result: list[uuid.UUID] = []
    for value in values:
        parsed = _try_uuid(value)
        if parsed:
            result.append(parsed)
    return result


def reserve_budget_persistent(project_id: str | None, estimated_tokens: int) -> tuple[bool, int]:
    project_uuid = _try_uuid(project_id)
    if not project_uuid:
        return reserve_budget(project_id, estimated_tokens)

    try:
        with SessionLocal() as db:
            stmt = select(Project).where(Project.id == project_uuid).with_for_update()
            project = db.execute(stmt).scalar_one_or_none()
            if not project:
                return reserve_budget(project_id, estimated_tokens)

            total = int(project.token_budget_total or 0)
            used = int(project.token_budget_used or 0)
            remaining = max(0, total - used)
            if estimated_tokens > remaining:
                return (False, remaining)

            project.token_budget_used = used + estimated_tokens
            db.add(project)
            db.commit()
            return (True, max(0, total - int(project.token_budget_used or 0)))
    except SQLAlchemyError:
        return reserve_budget(project_id, estimated_tokens)


def log_llm_call(
    *,
    project_id: str | None,
    model_name: str,
    purpose: str,
    provider_profile_id: str | None,
    evidence_ids: list[str],
    prompt_text: str,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int,
    budget_remaining: int | None,
    retry_count: int = 0,
    fallback_count: int = 0,
    cache_hit: bool = False,
    pricing_blocked: bool = False,
    blocked_reason: str | None = None,
    actor_user_id: str = "system",
) -> None:
    project_uuid = _try_uuid(project_id)
    profile_uuid = _try_uuid(provider_profile_id)
    prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()

    try:
        with SessionLocal() as db:
            db.add(
                LLMCallLog(
                    project_id=project_uuid,
                    version_id=None,
                    actor_user_id=actor_user_id,
                    model_name=model_name,
                    purpose=purpose,
                    provider_profile_id=profile_uuid,
                    evidence_ids=_uuid_list(evidence_ids),
                    prompt_hash=prompt_hash,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    latency_ms=latency_ms,
                    budget_remaining=budget_remaining,
                    blocked_reason=blocked_reason,
                    retry_count=retry_count,
                    fallback_count=fallback_count,
                    cache_hit=cache_hit,
                    pricing_blocked=pricing_blocked,
                )
            )
            db.commit()
    except SQLAlchemyError:
        # Non-blocking audit path: generation should continue even if log persistence fails.
        return
