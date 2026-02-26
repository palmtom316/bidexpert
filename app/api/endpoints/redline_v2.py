from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    RedlineCheckRequest,
    RedlineOverrideRequest,
    RedlineOverrideResponse,
    RedlineReport,
)
from app.services.redline_engine import run_redline_check

_log = logging.getLogger(__name__)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


def _audit(action: str, *, actor: str = "system", project_id: str | None = None, target_id: str | None = None, meta: dict | None = None) -> bool:
    try:
        from app.services.audit_log import record_audit_event

        return bool(
            record_audit_event(
                action=action,
                actor_user_id=actor,
                project_id=project_id,
                target_id=target_id,
                metadata=meta,
            )
        )
    except Exception:
        _log.warning("audit write failed for %s", action, exc_info=True)
        return False


@router.post("/api/v2/redline/check", response_model=RedlineReport)
def run_g2_redline_check(payload: RedlineCheckRequest) -> RedlineReport:
    ctx = _ctx()
    report = run_redline_check(payload)
    _audit(
        "redline.check",
        actor=ctx._resolved_created_by(None),
        project_id=payload.project_id,
        target_id=payload.tender_package_id,
        meta={"status": report.status, "finding_count": len(report.findings)},
    )
    return report


@router.post("/api/v2/redline/override", response_model=RedlineOverrideResponse)
def apply_redline_override(payload: RedlineOverrideRequest) -> RedlineOverrideResponse:
    ctx = _ctx()
    has_p0 = any(item.severity == "P0" for item in payload.findings)
    if not has_p0:
        raise HTTPException(status_code=400, detail="override requires at least one P0 finding")

    override_id = str(uuid.uuid4())
    actor = ctx._resolved_created_by(payload.approved_by)
    audited = _audit(
        "redline.override",
        actor=actor,
        project_id=payload.project_id,
        target_id=payload.tender_package_id,
        meta={
            "override_id": override_id,
            "reason": payload.override_reason,
            "requested_approved_by": payload.approved_by,
            "finding_count": len(payload.findings),
        },
    )
    if not audited:
        raise HTTPException(status_code=503, detail="override audit persistence failed")
    return RedlineOverrideResponse(status="OVERRIDDEN", override_id=override_id, audited=True)
