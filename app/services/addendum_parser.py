from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models.tables import TenderAddendum


def parse_addendum_overrides(payload: str | dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    raw: Any = payload
    if isinstance(payload, str):
        raw = json.loads(payload)

    if isinstance(raw, dict):
        rows = raw.get("overrides", [])
    elif isinstance(raw, list):
        rows = raw
    else:
        rows = []

    normalized: list[dict[str, Any]] = []
    for item in rows if isinstance(rows, Iterable) else []:
        if not isinstance(item, dict):
            continue
        clause_no = str(item.get("clause_no") or item.get("clause_code") or "").strip()
        override_text = str(item.get("override_text") or item.get("text") or item.get("clause_text") or "").strip()
        if not clause_no or not override_text:
            continue

        impacted = item.get("impacted_chapters") or item.get("chapter_keys") or []
        if isinstance(impacted, list):
            impacted_chapters = [str(x).strip() for x in impacted if str(x).strip()]
        else:
            impacted_chapters = []

        normalized.append(
            {
                "clause_no": clause_no,
                "override_text": override_text,
                "impacted_chapters": impacted_chapters,
            }
        )

    return normalized


def persist_addendum_payload(
    db: Session,
    *,
    project_id: uuid.UUID,
    tender_id: str | None,
    addendum_code: str | None,
    payload: str | dict[str, Any] | list[dict[str, Any]],
) -> TenderAddendum:
    overrides = parse_addendum_overrides(payload)
    row = TenderAddendum(
        project_id=project_id,
        tender_id=tender_id,
        addendum_code=addendum_code,
        parsed_overrides_json={"overrides": overrides},
    )
    db.add(row)
    db.flush()
    return row


def persist_addendum_from_workspace(
    db: Session,
    *,
    project_id: uuid.UUID,
    tender_id: str,
    workspace: Path,
) -> TenderAddendum | None:
    path = workspace / "derived" / "addendum_overrides.json"
    if not path.is_file():
        return None

    payload = json.loads(path.read_text(encoding="utf-8"))
    addendum_code = None
    if isinstance(payload, dict):
        code = payload.get("addendum_code")
        if code is not None:
            addendum_code = str(code)

    return persist_addendum_payload(
        db,
        project_id=project_id,
        tender_id=tender_id,
        addendum_code=addendum_code,
        payload=payload,
    )
