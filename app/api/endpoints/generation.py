from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.handlers.workflow_generation_review import (
    enqueue_generate_draft_handler,
    generate_draft_handler,
    pricing_fuse_handler,
    sanitize_text_handler,
    validate_generation_handler,
)
from app.schemas.contracts import (
    DraftGenerationRequest,
    DraftGenerationResponse,
    EnqueueIngestResponse,
    GateValidationRequest,
    GateValidationResponse,
    PricingFuseRequest,
    PricingFuseResponse,
    SanitizeRequest,
    SanitizeResponse,
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


@router.post("/v1/policy/pricing-fuse", response_model=PricingFuseResponse)
def pricing_fuse(payload: PricingFuseRequest) -> PricingFuseResponse:
    ctx = _ctx()
    return pricing_fuse_handler(payload, detect_pricing_content_fn=ctx.detect_pricing_content)


@router.post("/v1/policy/sanitize", response_model=SanitizeResponse)
def sanitize_text(payload: SanitizeRequest) -> SanitizeResponse:
    ctx = _ctx()
    return sanitize_text_handler(
        payload,
        sanitize_outbound_text_fn=ctx.sanitize_outbound_text,
    )


@router.post("/v1/generation/validate", response_model=GateValidationResponse)
def validate_generation(payload: GateValidationRequest) -> GateValidationResponse:
    ctx = _ctx()
    return validate_generation_handler(
        payload,
        run_three_gates_fn=ctx.run_three_gates,
        coverage_threshold=ctx.settings.min_matrix_coverage,
    )


@router.post("/v1/generation/draft", response_model=DraftGenerationResponse)
def generate_draft(payload: DraftGenerationRequest) -> DraftGenerationResponse:
    ctx = _ctx()
    result = generate_draft_handler(
        payload,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        generate_draft_with_retrieval_fn=ctx.generate_draft_with_retrieval,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("generation.draft", target_id=getattr(payload, "outline_id", None), meta={"section_key": getattr(payload, "section_key", None)})
    return result


@router.post("/v1/tasks/generate-draft", response_model=EnqueueIngestResponse)
def enqueue_generate_draft(payload: DraftGenerationRequest) -> EnqueueIngestResponse:
    ctx = _ctx()
    return enqueue_generate_draft_handler(
        payload,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        generate_draft_task_obj=ctx.generate_draft_task,
    )
