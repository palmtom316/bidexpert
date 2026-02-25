from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.handlers.workflow_generation_review import (
    calculate_score_handler,
    confirm_outline_handler,
    confirm_section_handler,
    create_outline_handler,
    enqueue_section_workflow_handler,
    review_full_handler,
    review_section_handler,
)
from app.schemas.contracts import (
    OutlineConfirmRequest,
    OutlineConfirmResponse,
    OutlineCreateRequest,
    OutlineCreateResponse,
    ReviewFullRequest,
    ReviewReportResponse,
    ReviewSectionRequest,
    ScoringReportResponse,
    ScoringRequest,
    SectionConfirmRequest,
    SectionConfirmResponse,
    WorkflowSectionRequest,
    WorkflowSectionResponse,
)

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


@router.post("/v1/workflow/outline", response_model=OutlineCreateResponse)
def create_outline(payload: OutlineCreateRequest) -> OutlineCreateResponse:
    ctx = _ctx()
    result = create_outline_handler(
        payload,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        create_outline_run_fn=ctx.create_outline_run,
    )
    _audit("workflow.create_outline", project_id=getattr(payload, "project_id", None), target_id=getattr(result, "outline_id", None))
    return result


@router.post("/v1/workflow/outline/confirm", response_model=OutlineConfirmResponse)
def confirm_outline(payload: OutlineConfirmRequest) -> OutlineConfirmResponse:
    ctx = _ctx()
    result = confirm_outline_handler(
        payload,
        confirm_outline_run_fn=ctx.confirm_outline_run,
    )
    _audit("workflow.confirm_outline", target_id=getattr(payload, "outline_id", None))
    return result


@router.post("/v1/workflow/section", response_model=WorkflowSectionResponse)
def enqueue_section_workflow(payload: WorkflowSectionRequest) -> WorkflowSectionResponse:
    ctx = _ctx()
    return enqueue_section_workflow_handler(
        payload,
        get_outline_status_fn=ctx.get_outline_status,
        get_resume_from_step_fn=ctx.get_resume_from_step,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        chain_fn=ctx.chain,
        section_extract_stage_task_obj=ctx.section_extract_stage_task,
        section_generate_stage_task_obj=ctx.section_generate_stage_task,
        section_validate_stage_task_obj=ctx.section_validate_stage_task,
        section_render_stage_task_obj=ctx.section_render_stage_task,
        mark_section_pending_fn=ctx.mark_section_pending,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/workflow/section/confirm", response_model=SectionConfirmResponse)
def confirm_section(payload: SectionConfirmRequest) -> SectionConfirmResponse:
    ctx = _ctx()
    result = confirm_section_handler(payload, confirm_section_run_fn=ctx.confirm_section_run)
    _audit("workflow.confirm_section", target_id=getattr(payload, "outline_id", None), meta={"section_key": getattr(payload, "section_key", None)})
    return result


@router.post("/v1/workflow/section/review", response_model=ReviewReportResponse)
def review_section_api(payload: ReviewSectionRequest) -> ReviewReportResponse:
    ctx = _ctx()
    result = review_section_handler(
        payload,
        run_compliance_review_fn=ctx.run_compliance_review,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("workflow.review_section", target_id=getattr(payload, "outline_id", None), meta={"section_key": getattr(payload, "section_key", None)})
    return result


@router.post("/v1/workflow/review/full", response_model=ReviewReportResponse)
def review_full_api(payload: ReviewFullRequest) -> ReviewReportResponse:
    ctx = _ctx()
    result = review_full_handler(
        payload,
        run_full_compliance_review_fn=ctx.run_full_compliance_review,
        review_ensemble_enabled=ctx.settings.review_ensemble_enabled,
        review_ensemble_size=ctx.settings.review_ensemble_size,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("workflow.review_full", target_id=getattr(payload, "outline_id", None))
    return result


@router.post("/v1/workflow/scoring/calculate", response_model=ScoringReportResponse)
def calculate_score_api(payload: ScoringRequest) -> ScoringReportResponse:
    ctx = _ctx()
    result = calculate_score_handler(
        payload,
        run_scoring_service_fn=ctx.run_scoring_service,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("workflow.calculate_score", target_id=getattr(payload, "outline_id", None))
    return result
