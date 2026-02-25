from __future__ import annotations

import logging

from fastapi import APIRouter

from app.api.handlers.evidence_expert_render import render_doc_handler, render_structured_doc_handler
from app.schemas.contracts import (
    RenderWordRequest,
    RenderWordResponse,
    RenderWordStructuredRequest,
    RenderWordStructuredResponse,
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


@router.post("/v1/render/word", response_model=RenderWordResponse)
def render_doc(payload: RenderWordRequest) -> RenderWordResponse:
    ctx = _ctx()
    result = render_doc_handler(
        payload,
        resolve_within_base_fn=ctx._resolve_within_base,
        render_word_fn=ctx.render_word,
        render_output_dir=ctx.settings.render_output_dir,
        render_template_dir=ctx.settings.render_template_dir,
    )
    _audit("render.word", meta={"output_path": getattr(result, "output_path", None)})
    return result


@router.post("/v1/render/word/structured", response_model=RenderWordStructuredResponse)
def render_structured_doc(payload: RenderWordStructuredRequest) -> RenderWordStructuredResponse:
    ctx = _ctx()
    result = render_structured_doc_handler(
        payload,
        resolve_within_base_fn=ctx._resolve_within_base,
        render_word_structured_fn=ctx.render_word_structured,
        render_output_dir=ctx.settings.render_output_dir,
        render_template_dir=ctx.settings.render_template_dir,
    )
    _audit("render.word_structured", meta={"output_path": getattr(result, "output_path", None)})
    return result
