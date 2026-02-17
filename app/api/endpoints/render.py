from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers.evidence_expert_render import render_doc_handler, render_structured_doc_handler
from app.schemas.contracts import (
    RenderWordRequest,
    RenderWordResponse,
    RenderWordStructuredRequest,
    RenderWordStructuredResponse,
)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


@router.post("/v1/render/word", response_model=RenderWordResponse)
def render_doc(payload: RenderWordRequest) -> RenderWordResponse:
    ctx = _ctx()
    return render_doc_handler(
        payload,
        resolve_within_base_fn=ctx._resolve_within_base,
        render_word_fn=ctx.render_word,
        render_output_dir=ctx.settings.render_output_dir,
        render_template_dir=ctx.settings.render_template_dir,
    )


@router.post("/v1/render/word/structured", response_model=RenderWordStructuredResponse)
def render_structured_doc(payload: RenderWordStructuredRequest) -> RenderWordStructuredResponse:
    ctx = _ctx()
    return render_structured_doc_handler(
        payload,
        resolve_within_base_fn=ctx._resolve_within_base,
        render_word_structured_fn=ctx.render_word_structured,
        render_output_dir=ctx.settings.render_output_dir,
        render_template_dir=ctx.settings.render_template_dir,
    )
