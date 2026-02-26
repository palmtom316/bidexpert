from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.contracts import (
    ScorecardConfirmRequest,
    ScorecardConfirmResponse,
    ScorecardParseRequest,
    ScorecardParseResponse,
)
from app.services.scorecard_parser import confirm_scorecard, parse_scorecard

_log = logging.getLogger(__name__)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


def _audit(action: str, *, actor: str = "system", project_id: str | None = None, target_id: str | None = None, meta: dict | None = None) -> None:
    try:
        from app.services.audit_log import record_audit_event

        record_audit_event(action=action, actor_user_id=actor, project_id=project_id, target_id=target_id, metadata=meta)
    except Exception:
        _log.warning("audit write failed for %s", action, exc_info=True)


@router.post("/api/v2/scorecard/parse", response_model=ScorecardParseResponse)
def parse_scorecard_v2(payload: ScorecardParseRequest) -> ScorecardParseResponse:
    ctx = _ctx()
    result = parse_scorecard(
        project_id=payload.project_id,
        tender_text=payload.tender_text,
    )
    _audit(
        "scorecard.parse",
        actor=ctx._resolved_created_by(None),
        project_id=payload.project_id,
        target_id=result["scorecard_id"],
        meta={"table_block_count": len(result["table_blocks"])},
    )
    return ScorecardParseResponse(**result)


@router.post("/api/v2/scorecard/confirm", response_model=ScorecardConfirmResponse)
def confirm_scorecard_v2(payload: ScorecardConfirmRequest) -> ScorecardConfirmResponse:
    ctx = _ctx()
    actor = ctx._resolved_created_by(payload.reviewer)
    try:
        result = confirm_scorecard(
            scorecard_id=payload.scorecard_id,
            project_id=payload.project_id,
            approved=payload.approved,
            reviewer=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(
        "scorecard.confirm",
        actor=actor,
        target_id=payload.scorecard_id,
        meta={"approved": payload.approved},
    )
    return ScorecardConfirmResponse(**result)
