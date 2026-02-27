from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from pathlib import Path
from time import monotonic

from celery.exceptions import CeleryError
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas.contracts import (
    BatchIngestDirectoryRequest,
    BatchIngestDirectoryResponse,
    DraftGenerationRequest,
    DraftGenerationResponse,
    EnqueueIngestResponse,
    GateValidationRequest,
    GateValidationResponse,
    IngestUploadResponse,
    OutlineConfirmRequest,
    OutlineConfirmResponse,
    OutlineCreateRequest,
    OutlineCreateResponse,
    PricingFuseRequest,
    PricingFuseResponse,
    ReviewFullRequest,
    ReviewReportResponse,
    ReviewSectionRequest,
    SanitizeRequest,
    SanitizeResponse,
    ScoringReportResponse,
    ScoringRequest,
    SectionConfirmRequest,
    SectionConfirmResponse,
    TaskStatusResponse,
    WorkflowSectionRequest,
    WorkflowSectionResponse,
)
from app.services.path_safety import validate_path_identifier


def create_outline_handler(
    payload: OutlineCreateRequest,
    *,
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    create_outline_run_fn: Callable[[str, str], tuple[str, list[dict], str]],
) -> OutlineCreateResponse:
    blocked, reasons = detect_pricing_content_fn(payload.tender_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    outline_id, sections, status = create_outline_run_fn(payload.project_id, payload.tender_text)
    return OutlineCreateResponse(
        outline_id=outline_id,
        project_id=payload.project_id,
        status=status,
        sections=sections,
    )


def confirm_outline_handler(
    payload: OutlineConfirmRequest,
    *,
    confirm_outline_run_fn: Callable[[str, bool], str],
) -> OutlineConfirmResponse:
    try:
        status = confirm_outline_run_fn(payload.outline_id, payload.approved)
        return OutlineConfirmResponse(outline_id=payload.outline_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def ingest_tender_upload_handler(
    *,
    file: UploadFile,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    ingest_upload_request_fn: Callable[..., IngestUploadResponse],
    enable_ocr_fallback: bool,
) -> IngestUploadResponse:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="only .pdf/.docx is supported")

    return ingest_upload_request_fn(
        filename=filename,
        file_bytes=await read_upload_with_limit_fn(file),
        enable_ocr_fallback=enable_ocr_fallback,
    )


async def enqueue_ingest_handler(
    *,
    file: UploadFile,
    resolve_within_base_fn: Callable[..., Path],
    upload_dir: str,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    ingest_document_task_obj,
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> EnqueueIngestResponse:
    from uuid import uuid4

    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".pdf", ".docx"}:
        raise HTTPException(status_code=400, detail="only .pdf/.docx is supported")

    upload_dir_path = resolve_within_base_fn(".", Path(upload_dir))
    target = upload_dir_path / f"{uuid4()}_{filename}"
    target.write_bytes(await read_upload_with_limit_fn(file))

    try:
        task = ingest_document_task_obj.delay(str(target))
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except CeleryError as exc:
        raise service_unavailable_exc_factory() from exc
    except OSError as exc:
        raise service_unavailable_exc_factory() from exc


def enqueue_ingest_directory_handler(
    payload: BatchIngestDirectoryRequest,
    *,
    resolve_within_base_fn: Callable[..., Path],
    upload_dir: str,
    ingest_document_task_obj,
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> BatchIngestDirectoryResponse:
    directory = resolve_within_base_fn(
        payload.directory,
        Path(upload_dir),
        require_exists=True,
        require_directory=True,
    )

    allowed_files = [item for item in directory.rglob("*") if item.is_file() and item.suffix.lower() in {".pdf", ".docx"}]
    if not allowed_files:
        return BatchIngestDirectoryResponse(status="PENDING", total_files=0, task_ids=[])

    task_ids: list[str] = []
    try:
        for file_path in sorted(allowed_files):
            task = ingest_document_task_obj.delay(str(file_path))
            task_ids.append(task.id)
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc

    return BatchIngestDirectoryResponse(status="PENDING", total_files=len(allowed_files), task_ids=task_ids)


def task_status_handler(
    task_id: str,
    *,
    get_task_result_fn: Callable[[str], dict],
) -> TaskStatusResponse:
    return TaskStatusResponse(**get_task_result_fn(task_id))


async def task_status_stream_handler(
    task_id: str,
    *,
    get_task_result_fn: Callable[[str], dict],
    timeout_seconds: int,
) -> StreamingResponse:
    timeout_seconds = max(1, int(timeout_seconds))
    deadline = monotonic() + timeout_seconds

    async def events() -> AsyncGenerator[str, None]:
        terminal = {"SUCCESS", "FAILURE", "REVOKED"}
        while monotonic() < deadline:
            result = get_task_result_fn(task_id)
            yield f"data: {json.dumps(result, ensure_ascii=False)}\n\n"
            if result["status"] in terminal:
                break
            await asyncio.sleep(1)
        else:
            timeout_payload = {
                "task_id": task_id,
                "status": "TIMEOUT",
                "result": {"detail": f"stream timeout after {timeout_seconds}s"},
            }
            yield f"data: {json.dumps(timeout_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


def pricing_fuse_handler(
    payload: PricingFuseRequest,
    *,
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
) -> PricingFuseResponse:
    blocked, reasons = detect_pricing_content_fn(payload.text)
    return PricingFuseResponse(blocked=blocked, reasons=reasons)


def sanitize_text_handler(
    payload: SanitizeRequest,
    *,
    sanitize_outbound_text_fn: Callable[..., object],
) -> SanitizeResponse:
    result = sanitize_outbound_text_fn(
        text=payload.text,
        sensitive_strategy=payload.strategy,
        allowlist=payload.allowlist,
    )
    return SanitizeResponse(
        blocked=result.pricing_blocked,
        warnings=result.warnings,
        sanitized_text=result.text,
    )


def validate_generation_handler(
    payload: GateValidationRequest,
    *,
    run_three_gates_fn: Callable[..., object],
    coverage_threshold: float,
) -> GateValidationResponse:
    evidence_map = {item.evidence_id: item.text for item in payload.evidence}
    evidence_texts = [evidence_map[eid] for eid in payload.evidence_ids if eid in evidence_map]
    result = run_three_gates_fn(
        generated_text=payload.generated_text,
        evidence_ids=payload.evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=1,
        requirement_total=1,
        coverage_threshold=coverage_threshold,
    )
    return GateValidationResponse(
        status=result.status,
        missing_sentences=result.missing_sentences,
        coverage=result.coverage,
    )


def generate_draft_handler(
    payload: DraftGenerationRequest,
    *,
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    generate_draft_with_retrieval_fn: Callable[..., DraftGenerationResponse],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> DraftGenerationResponse:
    blocked, reasons = detect_pricing_content_fn(payload.requirement_text)
    if blocked:
        return DraftGenerationResponse(
            generated_text="BLOCKED_PRICING_CONTENT",
            evidence_ids=[],
            status="BLOCKED_PRICING_CONTENT",
            missing_sentences=["pricing_blocked"],
            coverage=0.0,
            warnings=reasons,
            coverage_map={},
        )

    try:
        return generate_draft_with_retrieval_fn(
            requirement_id=payload.requirement_id,
            requirement_text=payload.requirement_text,
            top_k=payload.top_k,
            project_id=payload.project_id,
            industry_tag=payload.industry_tag,
            tender_template_id=payload.tender_template_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


def enqueue_generate_draft_handler(
    payload: DraftGenerationRequest,
    *,
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    generate_draft_task_obj,
) -> EnqueueIngestResponse:
    blocked, reasons = detect_pricing_content_fn(payload.requirement_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    task = generate_draft_task_obj.delay(
        payload.requirement_id,
        payload.requirement_text,
        payload.top_k,
        payload.project_id,
        payload.industry_tag,
        payload.tender_template_id,
    )
    return EnqueueIngestResponse(task_id=task.id, status="PENDING")


def enqueue_section_workflow_handler(
    payload: WorkflowSectionRequest,
    *,
    get_outline_status_fn: Callable[[str], str | None],
    get_resume_from_step_fn: Callable[[str], str],
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    chain_fn,
    section_extract_stage_task_obj,
    section_generate_stage_task_obj,
    section_validate_stage_task_obj,
    section_render_stage_task_obj,
    mark_section_pending_fn: Callable[[str, str], None],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> WorkflowSectionResponse:
    try:
        validate_path_identifier("outline_id", payload.outline_id)
        validate_path_identifier("section_key", payload.section_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    outline_status = get_outline_status_fn(payload.outline_id)
    if outline_status is None:
        raise HTTPException(status_code=404, detail="outline not found")
    if outline_status != "OUTLINE_CONFIRMED":
        raise HTTPException(status_code=400, detail="outline not confirmed")

    req_text = "。".join(payload.requirement_texts)
    blocked, reasons = detect_pricing_content_fn(req_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    try:
        resume_from_step = get_resume_from_step_fn(payload.outline_id)
    except ValueError:
        resume_from_step = "G1"

    try:
        stage_chain = chain_fn(
            section_extract_stage_task_obj.s(
                payload.outline_id,
                payload.project_id,
                payload.section_key,
                req_text,
                payload.industry_tag,
                resume_from_step,
                payload.section_title,
            ),
            section_generate_stage_task_obj.s(),
            section_validate_stage_task_obj.s(),
            section_render_stage_task_obj.s(),
        )
        pipeline_task = stage_chain.apply_async()
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc
    mark_section_pending_fn(payload.outline_id, payload.section_key)

    return WorkflowSectionResponse(
        section_key=payload.section_key,
        status="PENDING",
        task_ids={"SECTION_PIPELINE": pipeline_task.id},
    )


def confirm_section_handler(
    payload: SectionConfirmRequest,
    *,
    confirm_section_run_fn: Callable[[str, str, bool], str],
) -> SectionConfirmResponse:
    try:
        validate_path_identifier("outline_id", payload.outline_id)
        validate_path_identifier("section_key", payload.section_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        status = confirm_section_run_fn(payload.outline_id, payload.section_key, payload.approved)
        return SectionConfirmResponse(
            outline_id=payload.outline_id,
            section_key=payload.section_key,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def review_section_handler(
    payload: ReviewSectionRequest,
    *,
    run_compliance_review_fn: Callable[[str, str, str | None], object],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ReviewReportResponse:
    try:
        report = run_compliance_review_fn(payload.project_id, payload.section_key, payload.outline_id)
        return ReviewReportResponse(
            id=str(report.id),
            project_id=str(report.project_id),
            section_key=str(report.section_key),
            status=str(report.status),
            report_json=report.report_json,
            created_at=report.created_at.isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def review_full_handler(
    payload: ReviewFullRequest,
    *,
    run_full_compliance_review_fn: Callable[..., object],
    review_ensemble_enabled: bool,
    review_ensemble_size: int,
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ReviewReportResponse:
    try:
        enable_ensemble = bool(payload.enable_ensemble or review_ensemble_enabled)
        ensemble_size = payload.ensemble_size or review_ensemble_size
        report = run_full_compliance_review_fn(
            payload.project_id,
            payload.outline_id,
            enable_ensemble=enable_ensemble,
            ensemble_size=ensemble_size,
        )
        return ReviewReportResponse(
            id=str(report.id),
            project_id=str(report.project_id),
            section_key=str(report.section_key),
            status=str(report.status),
            report_json=report.report_json,
            created_at=report.created_at.isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def calculate_score_handler(
    payload: ScoringRequest,
    *,
    run_scoring_service_fn: Callable[[str], object],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> ScoringReportResponse:
    try:
        report = run_scoring_service_fn(payload.project_id)
        return ScoringReportResponse(
            id=str(report.id),
            project_id=str(report.project_id),
            score_total=float(report.score_total),
            details_json=report.details_json,
            created_at=report.created_at.isoformat(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc
