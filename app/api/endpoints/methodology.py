from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.api.handlers.methodology import (
    methodology_extract_handler,
    methodology_publish_handler,
    methodology_review_handler,
    methodology_run_handler,
)
from app.schemas.contracts import (
    MethodologyExtractRequest,
    MethodologyExtractResponse,
    MethodologyPublishResponse,
    MethodologyReviewRequest,
    MethodologyReviewResponse,
    MethodologyRunResponse,
    MethodologyRunResultResponse,
    MethodologySearchRequest,
    MethodologySearchResponse,
    MethodologySnippetItem,
    MethodologySnippetListResponse,
)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


@router.post("/api/methodology/extract", response_model=MethodologyExtractResponse)
def methodology_extract(payload: MethodologyExtractRequest) -> MethodologyExtractResponse:
    ctx = _ctx()
    return methodology_extract_handler(
        payload,
        create_methodology_extract_run_fn=ctx.create_methodology_extract_run,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/api/methodology/extract-upload", response_model=MethodologyExtractResponse)
async def methodology_extract_upload(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    source_note: str | None = Form(default=None),
    domain: str | None = Form(default=None),
    tags: str | None = Form(default=None),
) -> MethodologyExtractResponse:
    ctx = _ctx()
    try:
        content = await ctx._read_upload_with_limit(file)
        parsed_tags = [item.strip() for item in (tags or "").split(",") if item.strip()]
        run_id = ctx.create_methodology_extract_run_from_file(
            filename=file.filename or "",
            content=content,
            source_type=source_type,
            source_note=source_note,
            domain=domain,
            tags=parsed_tags,
            created_by=ctx._resolved_created_by(None),
        )
        return MethodologyExtractResponse(run_id=run_id, status="RECEIVED")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise ctx._service_unavailable() from exc


@router.get("/api/methodology/runs/{run_id}", response_model=MethodologyRunResponse)
def methodology_run(run_id: str) -> MethodologyRunResponse:
    ctx = _ctx()
    return methodology_run_handler(
        run_id,
        get_methodology_run_fn=ctx.get_methodology_run,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/api/methodology/runs/{run_id}/result", response_model=MethodologyRunResultResponse)
def methodology_run_result(run_id: str) -> MethodologyRunResultResponse:
    ctx = _ctx()
    try:
        payload = ctx.get_methodology_run_result(run_id)
        return MethodologyRunResultResponse(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise ctx._service_unavailable() from exc


@router.post("/api/methodology/runs/{run_id}/review", response_model=MethodologyReviewResponse)
def methodology_review(run_id: str, payload: MethodologyReviewRequest) -> MethodologyReviewResponse:
    ctx = _ctx()
    return methodology_review_handler(
        run_id,
        payload,
        review_methodology_run_fn=ctx.review_methodology_run,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/api/methodology/runs/{run_id}/publish", response_model=MethodologyPublishResponse)
def methodology_publish(run_id: str) -> MethodologyPublishResponse:
    ctx = _ctx()
    return methodology_publish_handler(
        run_id,
        publish_methodology_run_fn=ctx.publish_methodology_run,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/api/methodology/snippets", response_model=MethodologySnippetListResponse)
def methodology_snippets(tag: str | None = None, domain: str | None = None, limit: int = 50) -> MethodologySnippetListResponse:
    ctx = _ctx()
    try:
        items = ctx.list_methodology_snippets(domain=domain, tag=tag, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise ctx._service_unavailable() from exc

    return MethodologySnippetListResponse(
        items=[
            MethodologySnippetItem(
                snippet_id=row.snippet_id,
                title=row.title,
                domain=row.domain,
                tags=list(row.tags or []),
                risk_level=row.risk_level.value if hasattr(row.risk_level, "value") else str(row.risk_level),
                review_status=row.review_status.value if hasattr(row.review_status, "value") else str(row.review_status),
                source_type=row.source_type,
                created_at=row.created_at.isoformat() if row.created_at else "",
            )
            for row in items
        ]
    )


@router.post("/api/methodology/search", response_model=MethodologySearchResponse)
def methodology_search(payload: MethodologySearchRequest) -> MethodologySearchResponse:
    ctx = _ctx()
    try:
        result = ctx.search_methodology_snippets(
            query=payload.query,
            top_k=payload.top_k,
            domain=payload.domain,
        )
        return MethodologySearchResponse(hits=result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise ctx._service_unavailable() from exc
