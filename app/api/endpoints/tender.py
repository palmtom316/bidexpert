from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.api.handlers.provider_completed_tender import (
    analyze_tender_upload_handler,
    get_tender_analysis_detail_handler,
    list_tender_analysis_runs_handler,
    parse_tender_handler,
)
from app.api.handlers.workflow_generation_review import ingest_tender_upload_handler
from app.schemas.contracts import (
    IngestUploadResponse,
    ParseTenderRequest,
    ParseTenderResponse,
    TenderAnalyzeUploadResponse,
    TenderAnalysisDetailResponse,
    TenderAnalysisRunListResponse,
)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


@router.post("/v1/tender/parse", response_model=ParseTenderResponse)
def parse_tender(payload: ParseTenderRequest) -> ParseTenderResponse:
    ctx = _ctx()
    return parse_tender_handler(
        payload,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        parse_tender_requirements_fn=ctx.parse_tender_requirements,
    )


@router.post("/v1/tender/analyze-upload", response_model=TenderAnalyzeUploadResponse)
async def analyze_tender_upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    created_by: str = Form(default="system"),
) -> TenderAnalyzeUploadResponse:
    ctx = _ctx()
    return await analyze_tender_upload_handler(
        file=file,
        project_id=project_id,
        created_by=created_by,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        analyze_and_persist_tender_pdf_fn=ctx.analyze_and_persist_tender_pdf,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/v1/tender/analysis-runs", response_model=TenderAnalysisRunListResponse)
def list_tender_analysis_runs_api(project_id: str | None = None, limit: int = 50) -> TenderAnalysisRunListResponse:
    ctx = _ctx()
    return list_tender_analysis_runs_handler(
        project_id=project_id,
        limit=limit,
        list_tender_analysis_runs_fn=ctx.list_tender_analysis_runs,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/v1/tender/analysis-runs/{run_id}", response_model=TenderAnalysisDetailResponse)
def get_tender_analysis_detail_api(run_id: str) -> TenderAnalysisDetailResponse:
    ctx = _ctx()
    return get_tender_analysis_detail_handler(
        run_id=run_id,
        get_tender_analysis_detail_fn=ctx.get_tender_analysis_detail,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/tender/ingest-upload", response_model=IngestUploadResponse)
async def ingest_tender_upload(file: UploadFile = File(...)) -> IngestUploadResponse:
    ctx = _ctx()
    return await ingest_tender_upload_handler(
        file=file,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        ingest_upload_request_fn=ctx.ingest_upload_request,
        enable_ocr_fallback=ctx.settings.enable_ocr_fallback,
    )
