from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, UploadFile

from app.api.handlers.evidence_expert_render import (
    cache_invalidate_handler,
    evidence_extract_upsert_handler,
    evidence_search_handler,
    evidence_upsert_handler,
    expert_library_convert_confirm_handler,
    expert_library_convert_upload_handler,
    expert_library_doc_chunks_handler,
    expert_library_docs_handler,
    expert_library_ingest_structured_handler,
    expert_library_ingest_upload_handler,
    expert_library_ingest_uploads_handler,
    feedback_upsert_section_handler,
)
from app.schemas.contracts import (
    EnqueueIngestResponse,
    ExpertLibraryBatchIngestResponse,
    ExpertLibraryChunkListResponse,
    ExpertLibraryConvertConfirmRequest,
    ExpertLibraryConvertResponse,
    ExpertLibraryDocListResponse,
    ExpertLibraryIngestResponse,
    ExpertLibraryStructuredIngestRequest,
    ExpertLibraryStructuredIngestResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceUpsertRequest,
    HistoricalExtractRequest,
    PricingFuseResponse,
    SectionFeedbackUpsertRequest,
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


@router.post("/v1/evidence/upsert", response_model=EnqueueIngestResponse)
def evidence_upsert(payload: EvidenceUpsertRequest) -> EnqueueIngestResponse:
    ctx = _ctx()
    return evidence_upsert_handler(
        payload,
        upsert_evidence_task_obj=ctx.upsert_evidence_task,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/evidence/extract-upsert", response_model=EnqueueIngestResponse)
def evidence_extract_upsert(payload: HistoricalExtractRequest) -> EnqueueIngestResponse:
    ctx = _ctx()
    return evidence_extract_upsert_handler(
        payload,
        extract_upsert_historical_task_obj=ctx.extract_upsert_historical_task,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/expert-library/ingest-upload", response_model=ExpertLibraryIngestResponse)
async def expert_library_ingest_upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    industry_tag: str | None = Form(default=None),
    title: str | None = Form(default=None),
    created_by: str = Form(default="system"),
    doc_type: str = Form(default="EXPERT_HISTORY"),
    model_id: str | None = Form(default=None),
    ocr_provider: str | None = Form(default=None),
    ocr_api_key: str | None = Form(default=None),
    ocr_base_url: str | None = Form(default=None),
    ocr_model: str | None = Form(default=None),
) -> ExpertLibraryIngestResponse:
    ctx = _ctx()
    result = await expert_library_ingest_upload_handler(
        file=file,
        project_id=project_id,
        industry_tag=industry_tag,
        title=title,
        created_by=created_by,
        doc_type=doc_type,
        model_id=model_id,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        ingest_historical_pdf_fn=ctx.ingest_historical_pdf,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("expert_library.ingest_upload", actor=created_by, project_id=project_id, meta={"filename": file.filename, "doc_type": doc_type})
    return result


@router.post("/v1/expert-library/convert-upload", response_model=ExpertLibraryConvertResponse)
async def expert_library_convert_upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    industry_tag: str | None = Form(default=None),
    title: str | None = Form(default=None),
    created_by: str = Form(default="system"),
    doc_type: str = Form(default="EXPERT_HISTORY"),
    model_id: str | None = Form(default=None),
    ocr_provider: str | None = Form(default=None),
    ocr_api_key: str | None = Form(default=None),
    ocr_base_url: str | None = Form(default=None),
    ocr_model: str | None = Form(default=None),
) -> ExpertLibraryConvertResponse:
    ctx = _ctx()
    result = await expert_library_convert_upload_handler(
        file=file,
        project_id=project_id,
        industry_tag=industry_tag,
        title=title,
        created_by=created_by,
        doc_type=doc_type,
        model_id=model_id,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        convert_upload_to_structured_fn=ctx.convert_upload_to_structured,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("expert_library.convert_upload", actor=created_by, project_id=project_id, meta={"filename": file.filename})
    return result


@router.post("/v1/expert-library/convert-confirm", response_model=ExpertLibraryIngestResponse)
def expert_library_convert_confirm(payload: ExpertLibraryConvertConfirmRequest) -> ExpertLibraryIngestResponse:
    ctx = _ctx()
    result = expert_library_convert_confirm_handler(
        payload,
        confirm_structured_conversion_ingest_fn=ctx.confirm_structured_conversion_ingest,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("expert_library.convert_confirm", meta={"conversion_id": getattr(payload, "conversion_id", None)})
    return result


@router.post("/v1/expert-library/ingest-uploads", response_model=ExpertLibraryBatchIngestResponse)
async def expert_library_ingest_uploads(
    files: list[UploadFile] = File(...),
    project_id: str | None = Form(default=None),
    industry_tag: str | None = Form(default=None),
    title: str | None = Form(default=None),
    created_by: str = Form(default="system"),
    doc_type: str = Form(default="EXPERT_HISTORY"),
    model_id: str | None = Form(default=None),
    ocr_provider: str | None = Form(default=None),
    ocr_api_key: str | None = Form(default=None),
    ocr_base_url: str | None = Form(default=None),
    ocr_model: str | None = Form(default=None),
) -> ExpertLibraryBatchIngestResponse:
    ctx = _ctx()
    result = await expert_library_ingest_uploads_handler(
        files=files,
        project_id=project_id,
        industry_tag=industry_tag,
        title=title,
        created_by=created_by,
        doc_type=doc_type,
        model_id=model_id,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        ingest_historical_pdf_fn=ctx.ingest_historical_pdf,
        resolved_created_by_fn=ctx._resolved_created_by,
    )
    _audit("expert_library.ingest_uploads", actor=created_by, project_id=project_id, meta={"file_count": len(files), "doc_type": doc_type})
    return result


@router.post("/v1/expert-library/ingest-structured", response_model=ExpertLibraryStructuredIngestResponse)
def expert_library_ingest_structured(
    payload: ExpertLibraryStructuredIngestRequest,
) -> ExpertLibraryStructuredIngestResponse:
    ctx = _ctx()
    result = expert_library_ingest_structured_handler(
        payload,
        ingest_structured_expert_knowledge_fn=ctx.ingest_structured_expert_knowledge,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("expert_library.ingest_structured", project_id=getattr(payload, "project_id", None))
    return result


@router.get("/v1/expert-library/docs", response_model=ExpertLibraryDocListResponse)
def expert_library_docs(
    project_id: str | None = None,
    industry_tag: str | None = None,
    limit: int = 50,
) -> ExpertLibraryDocListResponse:
    ctx = _ctx()
    return expert_library_docs_handler(
        project_id=project_id,
        industry_tag=industry_tag,
        limit=limit,
        list_expert_docs_fn=ctx.list_expert_docs,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/v1/expert-library/docs/{expert_doc_id}/chunks", response_model=ExpertLibraryChunkListResponse)
def expert_library_doc_chunks(expert_doc_id: str, limit: int = 200) -> ExpertLibraryChunkListResponse:
    ctx = _ctx()
    return expert_library_doc_chunks_handler(
        expert_doc_id=expert_doc_id,
        limit=limit,
        list_expert_chunks_fn=ctx.list_expert_chunks,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/evidence/feedback-upsert", response_model=EnqueueIngestResponse)
def feedback_upsert_section(payload: SectionFeedbackUpsertRequest) -> EnqueueIngestResponse:
    ctx = _ctx()
    result = feedback_upsert_section_handler(
        payload,
        get_section_status_fn=ctx.get_section_status,
        detect_pricing_content_fn=ctx.detect_pricing_content,
        standardize_section_feedback_chunks_fn=ctx.standardize_section_feedback_chunks,
        upsert_evidence_task_obj=ctx.upsert_evidence_task,
    )
    _audit("evidence.feedback_upsert", meta={"outline_id": getattr(payload, "outline_id", None), "section_key": getattr(payload, "section_key", None)})
    return result


@router.post("/v1/evidence/search", response_model=EvidenceSearchResponse)
def evidence_search(payload: EvidenceSearchRequest) -> EvidenceSearchResponse:
    ctx = _ctx()
    return evidence_search_handler(
        payload,
        get_qdrant_store_fn=ctx.get_qdrant_store,
        to_search_hits_fn=ctx.to_search_hits,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.post("/v1/cache/invalidate", response_model=PricingFuseResponse)
def cache_invalidate(prefix: str | None = None) -> PricingFuseResponse:
    ctx = _ctx()
    return cache_invalidate_handler(prefix, invalidate_cache_fn=ctx.invalidate_cache)
