from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import GenerationVersion, MandatoryClause, SectionContent, TenderAddendum


def compute_effective_mandatory_clauses(
    db: Session,
    *,
    project_id: uuid.UUID,
    addendum: TenderAddendum | None,
) -> dict[str, dict[str, str]]:
    rows = db.execute(
        select(MandatoryClause).where(MandatoryClause.project_id == project_id)
    ).scalars().all()

    effective: dict[str, dict[str, str]] = {}
    for row in rows:
        code = (row.clause_code or "").strip()
        if not code:
            continue
        effective[code] = {"clause_text": row.clause_text, "source": "base"}

    overrides: Iterable[dict[str, Any]] = []
    if addendum and isinstance(addendum.parsed_overrides_json, dict):
        raw = addendum.parsed_overrides_json.get("overrides", [])
        if isinstance(raw, list):
            overrides = [item for item in raw if isinstance(item, dict)]

    for item in overrides:
        clause_no = str(item.get("clause_no") or "").strip()
        override_text = str(item.get("override_text") or "").strip()
        if clause_no and override_text:
            effective[clause_no] = {"clause_text": override_text, "source": "addendum"}

    return effective


def mark_generated_chapters_stale(
    db: Session,
    *,
    project_id: uuid.UUID,
    chapter_keys: list[str],
    addendum_code: str | None,
    version_id: uuid.UUID | None = None,
) -> list[str]:
    target_keys = [key.strip() for key in chapter_keys if key and key.strip()]
    if not target_keys:
        return []

    target_version_id = version_id
    if target_version_id is None:
        target_version_id = db.execute(
            select(GenerationVersion.id)
            .where(GenerationVersion.project_id == project_id)
            .order_by(GenerationVersion.version_no.desc(), GenerationVersion.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    if target_version_id is None:
        return []

    rows = db.execute(
        select(SectionContent).where(
            SectionContent.project_id == project_id,
            SectionContent.version_id == target_version_id,
            SectionContent.section_key.in_(target_keys),
        )
    ).scalars().all()

    stale: list[str] = []
    for row in rows:
        payload = dict(row.content_json or {})
        payload["stale_due_to_addendum"] = True
        payload["stale_addendum_code"] = addendum_code
        row.content_json = payload
        stale.append(row.section_key)

    db.flush()
    return sorted(set(stale))


def extract_impacted_chapters(addendum: TenderAddendum | None) -> list[str]:
    if not addendum or not isinstance(addendum.parsed_overrides_json, dict):
        return []
    raw = addendum.parsed_overrides_json.get("overrides", [])
    if not isinstance(raw, list):
        return []

    keys: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        impacted = item.get("impacted_chapters")
        if isinstance(impacted, list):
            keys.extend([str(v).strip() for v in impacted if str(v).strip()])
    return sorted(set(keys))
