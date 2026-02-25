from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

def ensure_publish_allowed(*, review_status: str, risk_level: str) -> None:
    normalized_status = (review_status or "").strip().lower()
    normalized_risk = (risk_level or "").strip().lower()

    if normalized_status != "approved":
        raise ValueError("review status must be approved")
    if normalized_risk == "high":
        raise ValueError("high risk snippet cannot be published")


def _build_snippet_id(*, run_id: str, created_at: datetime) -> str:
    year = created_at.year
    suffix = run_id.replace("-", "")[:8].upper()
    return f"MSNIP-{year}-{suffix}"


def publish_methodology_run(*, run_id: str, actor: str = "system") -> str:
    from app.db.session import session_scope
    from app.models.tables import MethodologyReviewStatus, MethodologySnippet
    from app.services.qdrant_store import get_qdrant_store

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise ValueError("invalid run_id") from exc

    with session_scope() as db:
        from app.models.tables import MethodologyRun

        run = db.get(MethodologyRun, run_uuid)
        if run is None:
            raise ValueError("run not found")

        review_status = run.review_status.value if hasattr(run.review_status, "value") else str(run.review_status)
        risk_level = run.risk_level.value if hasattr(run.risk_level, "value") else str(run.risk_level)
        ensure_publish_allowed(review_status=review_status, risk_level=risk_level)

        output_path = Path(run.output_json_path or "")
        if not output_path.exists():
            raise ValueError("run result not found")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid run result payload")

        now = datetime.now(UTC)
        snippet_id = _build_snippet_id(run_id=run_id, created_at=now)
        snippet = MethodologySnippet(
            snippet_id=snippet_id,
            run_id=run.id,
            title=str(payload.get("title") or "方法论条目"),
            domain=str(payload.get("domain") or "通用"),
            tags=list(payload.get("tags") or []),
            applicability=dict(payload.get("applicability") or {}),
            structure=list(payload.get("structure") or []),
            template_md=str(payload.get("template_md") or ""),
            payload=payload,
            risk_level=run.risk_level,
            review_status=MethodologyReviewStatus.APPROVED,
            source_type=run.source_type,
            source_note=run.source_note,
            created_by=(actor or "system").strip() or "system",
            reviewed_by=run.reviewer,
            reviewed_at=run.reviewed_at,
            created_at=now,
        )
        db.add(snippet)
        run.status = "PUBLISHED"
        db.commit()

    # Publish to methodology collection for retrieval.
    try:
        store = get_qdrant_store()
        store.upsert_methodology_snippet(
            snippet_id=snippet_id,
            title=str(payload.get("title") or "方法论条目"),
            domain=str(payload.get("domain") or "通用"),
            tags=list(payload.get("tags") or []),
            applicability=dict(payload.get("applicability") or {}),
            template_md=str(payload.get("template_md") or ""),
            risk_level=risk_level,
            review_status="approved",
            source_type=str(payload.get("source_type") or ""),
        )
    except Exception:
        # DB is the source of truth; search index can be repaired asynchronously.
        pass

    return snippet_id
