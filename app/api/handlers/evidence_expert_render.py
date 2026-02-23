from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from celery.exceptions import CeleryError
from fastapi import HTTPException, UploadFile

from app.schemas.contracts import (
    EnqueueIngestResponse,
    ExpertLibraryBatchIngestItem,
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
    RenderWordRequest,
    RenderWordResponse,
    RenderWordStructuredRequest,
    RenderWordStructuredResponse,
    SectionFeedbackUpsertRequest,
)
from app.services.path_safety import validate_path_identifier


def evidence_upsert_handler(
    payload: EvidenceUpsertRequest,
    *,
    upsert_evidence_task_obj,
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> EnqueueIngestResponse:
    try:
        task = upsert_evidence_task_obj.delay(payload.expert_doc_id, [item.model_dump() for item in payload.chunks])
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


def evidence_extract_upsert_handler(
    payload: HistoricalExtractRequest,
    *,
    extract_upsert_historical_task_obj,
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> EnqueueIngestResponse:
    try:
        task = extract_upsert_historical_task_obj.delay(
            payload.expert_doc_id,
            payload.text,
            payload.industry_tag,
            (payload.model_id or "").strip() or None,
        )
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


async def expert_library_ingest_upload_handler(
    *,
    file: UploadFile,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str,
    doc_type: str,
    model_id: str | None,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    ingest_historical_pdf_fn: Callable[..., ExpertLibraryIngestResponse],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> ExpertLibraryIngestResponse:
    try:
        resolved_ocr_provider = ocr_provider if isinstance(ocr_provider, str) else None
        resolved_ocr_api_key = ocr_api_key if isinstance(ocr_api_key, str) else None
        resolved_ocr_base_url = ocr_base_url if isinstance(ocr_base_url, str) else None
        resolved_ocr_model = ocr_model if isinstance(ocr_model, str) else None
        content = await read_upload_with_limit_fn(file)
        return ingest_historical_pdf_fn(
            filename=file.filename or "",
            content=content,
            project_id=project_id,
            industry_tag=industry_tag,
            title=title,
            created_by=resolved_created_by_fn(created_by),
            doc_type=doc_type,
            model_id=(model_id or "").strip() or None,
            ocr_provider=(resolved_ocr_provider or "").strip() or None,
            ocr_api_key=(resolved_ocr_api_key or "").strip() or None,
            ocr_base_url=(resolved_ocr_base_url or "").strip() or None,
            ocr_model=(resolved_ocr_model or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


async def expert_library_convert_upload_handler(
    *,
    file: UploadFile,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str,
    doc_type: str,
    model_id: str | None,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    convert_upload_to_structured_fn: Callable[..., ExpertLibraryConvertResponse],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> ExpertLibraryConvertResponse:
    try:
        resolved_ocr_provider = ocr_provider if isinstance(ocr_provider, str) else None
        resolved_ocr_api_key = ocr_api_key if isinstance(ocr_api_key, str) else None
        resolved_ocr_base_url = ocr_base_url if isinstance(ocr_base_url, str) else None
        resolved_ocr_model = ocr_model if isinstance(ocr_model, str) else None
        content = await read_upload_with_limit_fn(file)
        return convert_upload_to_structured_fn(
            filename=file.filename or "",
            content=content,
            project_id=project_id,
            industry_tag=industry_tag,
            title=title,
            created_by=resolved_created_by_fn(created_by),
            doc_type=doc_type,
            model_id=(model_id or "").strip() or None,
            ocr_provider=(resolved_ocr_provider or "").strip() or None,
            ocr_api_key=(resolved_ocr_api_key or "").strip() or None,
            ocr_base_url=(resolved_ocr_base_url or "").strip() or None,
            ocr_model=(resolved_ocr_model or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


def expert_library_convert_confirm_handler(
    payload: ExpertLibraryConvertConfirmRequest,
    *,
    confirm_structured_conversion_ingest_fn: Callable[..., ExpertLibraryIngestResponse],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ExpertLibraryIngestResponse:
    try:
        return confirm_structured_conversion_ingest_fn(
            conversion_id=payload.conversion_id,
            project_id=payload.project_id,
            industry_tag=payload.industry_tag,
            title=payload.title,
            created_by=resolved_created_by_fn(payload.created_by),
            doc_type=payload.doc_type,
            model_id=(payload.model_id or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


async def expert_library_ingest_uploads_handler(
    *,
    files: list[UploadFile],
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str,
    doc_type: str,
    model_id: str | None,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    ingest_historical_pdf_fn: Callable[..., ExpertLibraryIngestResponse],
    resolved_created_by_fn: Callable[[str | None], str],
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> ExpertLibraryBatchIngestResponse:
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    resolved_ocr_provider = ocr_provider if isinstance(ocr_provider, str) else None
    resolved_ocr_api_key = ocr_api_key if isinstance(ocr_api_key, str) else None
    resolved_ocr_base_url = ocr_base_url if isinstance(ocr_base_url, str) else None
    resolved_ocr_model = ocr_model if isinstance(ocr_model, str) else None
    items: list[ExpertLibraryBatchIngestItem] = []
    success_count = 0
    failure_count = 0
    for file in files:
        filename = file.filename or "unknown"
        try:
            content = await read_upload_with_limit_fn(file)
            result = ingest_historical_pdf_fn(
                filename=filename,
                content=content,
                project_id=project_id,
                industry_tag=industry_tag,
                title=title,
                created_by=resolved_created_by_fn(created_by),
                doc_type=doc_type,
                model_id=(model_id or "").strip() or None,
                ocr_provider=(resolved_ocr_provider or "").strip() or None,
                ocr_api_key=(resolved_ocr_api_key or "").strip() or None,
                ocr_base_url=(resolved_ocr_base_url or "").strip() or None,
                ocr_model=(resolved_ocr_model or "").strip() or None,
            )
            success_count += 1
            items.append(
                ExpertLibraryBatchIngestItem(
                    filename=result.filename,
                    status=result.status,
                    expert_doc_id=result.expert_doc_id,
                    source_document_id=result.source_document_id,
                    page_count=result.page_count,
                    chunk_count=result.chunk_count,
                    qdrant_upserted=result.qdrant_upserted,
                    warnings=result.warnings,
                )
            )
        except ValueError as exc:
            failure_count += 1
            items.append(
                ExpertLibraryBatchIngestItem(
                    filename=filename,
                    status="FAILED",
                    error=str(exc),
                )
            )
        except (RuntimeError, OSError):
            failure_count += 1
            items.append(
                ExpertLibraryBatchIngestItem(
                    filename=filename,
                    status="FAILED",
                    error="service temporarily unavailable",
                )
            )

    status = "SUCCEEDED"
    if success_count and failure_count:
        status = "PARTIAL_SUCCESS"
    elif failure_count and not success_count:
        status = "FAILED"

    return ExpertLibraryBatchIngestResponse(
        status=status,
        total_files=len(files),
        success_count=success_count,
        failure_count=failure_count,
        items=items,
    )


def expert_library_ingest_structured_handler(
    payload: ExpertLibraryStructuredIngestRequest,
    *,
    ingest_structured_expert_knowledge_fn: Callable[..., ExpertLibraryStructuredIngestResponse],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ExpertLibraryStructuredIngestResponse:
    try:
        return ingest_structured_expert_knowledge_fn(
            project_id=payload.project_id,
            industry_tag=payload.industry_tag,
            created_by=resolved_created_by_fn(payload.created_by),
            standard_items=payload.standard_items,
            company_performance_items=payload.company_performance_items,
            company_qualification_items=payload.company_qualification_items,
            pm_qualification_performance_items=payload.pm_qualification_performance_items,
            safety_production_items=payload.safety_production_items,
            quality_management_items=payload.quality_management_items,
            equipment_capability_items=payload.equipment_capability_items,
            financial_credit_items=payload.financial_credit_items,
            award_honors_items=payload.award_honors_items,
            service_commitment_items=payload.service_commitment_items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def expert_library_docs_handler(
    *,
    project_id: str | None,
    industry_tag: str | None,
    limit: int,
    list_expert_docs_fn: Callable[..., list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ExpertLibraryDocListResponse:
    try:
        items = list_expert_docs_fn(project_id=project_id, industry_tag=industry_tag, limit=limit)
        return ExpertLibraryDocListResponse(items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def expert_library_doc_chunks_handler(
    *,
    expert_doc_id: str,
    limit: int,
    list_expert_chunks_fn: Callable[..., list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ExpertLibraryChunkListResponse:
    try:
        items = list_expert_chunks_fn(expert_doc_id=expert_doc_id, limit=limit)
        return ExpertLibraryChunkListResponse(expert_doc_id=expert_doc_id, items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def feedback_upsert_section_handler(
    payload: SectionFeedbackUpsertRequest,
    *,
    get_section_status_fn: Callable[[str, str], str | None],
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    standardize_section_feedback_chunks_fn: Callable[..., list[object]],
    upsert_evidence_task_obj,
) -> EnqueueIngestResponse:
    try:
        validate_path_identifier("outline_id", payload.outline_id)
        validate_path_identifier("section_key", payload.section_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    section_status = get_section_status_fn(payload.outline_id, payload.section_key)
    if section_status != "SECTION_CONFIRMED":
        raise HTTPException(status_code=400, detail="section not confirmed")

    blocked, reasons = detect_pricing_content_fn(payload.content_md)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    chunks = standardize_section_feedback_chunks_fn(
        outline_id=payload.outline_id,
        section_key=payload.section_key,
        section_title=payload.section_title,
        content_md=payload.content_md,
        industry_tag=payload.industry_tag,
    )
    task = upsert_evidence_task_obj.delay(payload.expert_doc_id, [item.model_dump() for item in chunks])
    return EnqueueIngestResponse(task_id=task.id, status="PENDING")


def evidence_search_handler(
    payload: EvidenceSearchRequest,
    *,
    get_qdrant_store_fn: Callable[[], object],
    to_search_hits_fn: Callable[[list[object]], list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> EvidenceSearchResponse:
    try:
        store = get_qdrant_store_fn()
        hits = store.search(query=payload.query, top_k=payload.top_k, industry_tag=payload.industry_tag)
        return EvidenceSearchResponse(hits=to_search_hits_fn(hits))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


def cache_invalidate_handler(
    prefix: str | None,
    *,
    invalidate_cache_fn: Callable[[str | None], int],
) -> PricingFuseResponse:
    count = invalidate_cache_fn(prefix=prefix)
    return PricingFuseResponse(blocked=False, reasons=[f"invalidated={count}"])


def render_doc_handler(
    payload: RenderWordRequest,
    *,
    resolve_within_base_fn: Callable[[str, Path], Path],
    render_word_fn: Callable[..., str],
    render_output_dir: str,
    render_template_dir: str,
) -> RenderWordResponse:
    try:
        output_path = str(resolve_within_base_fn(payload.output_path, Path(render_output_dir)))
        template_path = (
            str(resolve_within_base_fn(payload.template_path, Path(render_template_dir)))
            if payload.template_path
            else None
        )
        output = render_word_fn(
            output_path=output_path,
            placeholders=payload.placeholders,
            template_path=template_path,
            style_config=payload.style_config,
        )
        return RenderWordResponse(output_path=output)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def render_structured_doc_handler(
    payload: RenderWordStructuredRequest,
    *,
    resolve_within_base_fn: Callable[[str, Path], Path],
    render_word_structured_fn: Callable[..., tuple[str, str | None]],
    render_output_dir: str,
    render_template_dir: str,
) -> RenderWordStructuredResponse:
    try:
        output_path = str(resolve_within_base_fn(payload.output_path, Path(render_output_dir)))
        template_path = (
            str(resolve_within_base_fn(payload.template_path, Path(render_template_dir)))
            if payload.template_path
            else None
        )
        output_path, pdf_path = render_word_structured_fn(
            output_path=output_path,
            content=payload.content.model_dump(mode="json"),
            placeholders=payload.placeholders,
            template_path=template_path,
            style_config=payload.style_config,
            export_pdf=payload.export_pdf,
        )
        return RenderWordStructuredResponse(output_path=output_path, pdf_path=pdf_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
