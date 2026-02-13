from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from celery.exceptions import CeleryError
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.contracts import (
    BatchIngestDirectoryRequest,
    BatchIngestDirectoryResponse,
    DraftGenerationRequest,
    DraftGenerationResponse,
    EnqueueIngestResponse,
    EvidenceSearchRequest,
    EvidenceSearchResponse,
    EvidenceUpsertRequest,
    GateValidationRequest,
    GateValidationResponse,
    HealthResponse,
    HistoricalExtractRequest,
    IngestUploadResponse,
    OutlineConfirmRequest,
    OutlineConfirmResponse,
    OutlineCreateRequest,
    OutlineCreateResponse,
    ParseTenderRequest,
    ParseTenderResponse,
    PricingFuseRequest,
    PricingFuseResponse,
    SanitizeRequest,
    SanitizeResponse,
    SectionFeedbackUpsertRequest,
    RenderWordRequest,
    RenderWordResponse,
    SectionConfirmRequest,
    SectionConfirmResponse,
    TaskStatusResponse,
    WorkflowSectionRequest,
    WorkflowSectionResponse,
)
from app.services.evidence_validator import run_three_gates
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.pdf_ingest import ingest_pdf_bytes
from app.services.pii_policy import sanitize_outbound_text
from app.services.pricing_guard import detect_pricing_content
from app.services.qdrant_store import QdrantStore, to_search_hits
from app.services.semantic_cache import invalidate_cache
from app.services.tender_parser import parse_tender_requirements
from app.services.knowledge_standardizer import standardize_section_feedback_chunks
from app.services.workflow_runs import (
    confirm_outline_run,
    confirm_section_run,
    create_outline_run,
    get_outline_status,
    get_section_status,
    mark_section_pending,
)
from app.services.word_renderer import render_word
from app.workers.tasks import (
    generate_draft_task,
    get_task_result,
    ingest_document_task,
    extract_upsert_historical_task,
    render_export_task,
    requirement_extract_task,
    section_generate_task,
    section_validate_task,
    upsert_evidence_task,
)

router = APIRouter()


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="service temporarily unavailable")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/v1/tender/parse", response_model=ParseTenderResponse)
def parse_tender(payload: ParseTenderRequest) -> ParseTenderResponse:
    blocked, reasons = detect_pricing_content(payload.text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    parsed = parse_tender_requirements(payload.text)
    return ParseTenderResponse(requirements=parsed.requirements, status=parsed.status)


@router.post("/v1/workflow/outline", response_model=OutlineCreateResponse)
def create_outline(payload: OutlineCreateRequest) -> OutlineCreateResponse:
    blocked, reasons = detect_pricing_content(payload.tender_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    outline_id, sections, status = create_outline_run(payload.project_id, payload.tender_text)
    return OutlineCreateResponse(
        outline_id=outline_id,
        project_id=payload.project_id,
        status=status,
        sections=sections,
    )


@router.post("/v1/workflow/outline/confirm", response_model=OutlineConfirmResponse)
def confirm_outline(payload: OutlineConfirmRequest) -> OutlineConfirmResponse:
    try:
        status = confirm_outline_run(payload.outline_id, payload.approved)
        return OutlineConfirmResponse(outline_id=payload.outline_id, status=status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/v1/tender/ingest-upload", response_model=IngestUploadResponse)
async def ingest_tender_upload(file: UploadFile = File(...)) -> IngestUploadResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported")

    result = ingest_pdf_bytes(
        filename=filename,
        pdf_bytes=await file.read(),
        enable_ocr_fallback=settings.enable_ocr_fallback,
    )
    return result


@router.post("/v1/tasks/ingest-upload", response_model=EnqueueIngestResponse)
async def enqueue_ingest(file: UploadFile = File(...)) -> EnqueueIngestResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / f"{uuid4()}_{filename}"
    target.write_bytes(await file.read())

    try:
        task = ingest_document_task.delay(str(target))
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except CeleryError as exc:
        raise _service_unavailable() from exc
    except OSError as exc:
        raise _service_unavailable() from exc


@router.post("/v1/tasks/ingest-directory", response_model=BatchIngestDirectoryResponse)
def enqueue_ingest_directory(payload: BatchIngestDirectoryRequest) -> BatchIngestDirectoryResponse:
    directory = Path(payload.directory)
    if not directory.exists() or not directory.is_dir():
        raise HTTPException(status_code=400, detail="directory not found")

    pdf_files = [item for item in directory.rglob("*") if item.is_file() and item.suffix.lower() == ".pdf"]
    if not pdf_files:
        return BatchIngestDirectoryResponse(status="PENDING", total_files=0, task_ids=[])

    task_ids: list[str] = []
    try:
        for file_path in sorted(pdf_files):
            task = ingest_document_task.delay(str(file_path))
            task_ids.append(task.id)
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc

    return BatchIngestDirectoryResponse(status="PENDING", total_files=len(pdf_files), task_ids=task_ids)


@router.get("/v1/tasks/{task_id}", response_model=TaskStatusResponse)
def task_status(task_id: str) -> TaskStatusResponse:
    return TaskStatusResponse(**get_task_result(task_id))


@router.get("/v1/tasks/{task_id}/stream")
async def task_status_stream(task_id: str) -> StreamingResponse:
    async def events() -> str:
        terminal = {"SUCCESS", "FAILURE", "REVOKED"}
        while True:
            result = get_task_result(task_id)
            yield f"data: {json.dumps(result, ensure_ascii=False)}\\n\\n"
            if result["status"] in terminal:
                break
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/v1/policy/pricing-fuse", response_model=PricingFuseResponse)
def pricing_fuse(payload: PricingFuseRequest) -> PricingFuseResponse:
    blocked, reasons = detect_pricing_content(payload.text)
    return PricingFuseResponse(blocked=blocked, reasons=reasons)


@router.post("/v1/policy/sanitize", response_model=SanitizeResponse)
def sanitize_text(payload: SanitizeRequest) -> SanitizeResponse:
    result = sanitize_outbound_text(
        text=payload.text,
        sensitive_strategy=payload.strategy,
        allowlist=payload.allowlist,
    )
    return SanitizeResponse(
        blocked=result.pricing_blocked,
        warnings=result.warnings,
        sanitized_text=result.text,
    )


@router.post("/v1/generation/validate", response_model=GateValidationResponse)
def validate_generation(payload: GateValidationRequest) -> GateValidationResponse:
    evidence_map = {item.evidence_id: item.text for item in payload.evidence}
    evidence_texts = [evidence_map[eid] for eid in payload.evidence_ids if eid in evidence_map]
    result = run_three_gates(
        generated_text=payload.generated_text,
        evidence_ids=payload.evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=1,
        requirement_total=1,
        coverage_threshold=settings.min_matrix_coverage,
    )
    return GateValidationResponse(
        status=result.status,
        missing_sentences=result.missing_sentences,
        coverage=result.coverage,
    )


@router.post("/v1/generation/draft", response_model=DraftGenerationResponse)
def generate_draft(payload: DraftGenerationRequest) -> DraftGenerationResponse:
    blocked, reasons = detect_pricing_content(payload.requirement_text)
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
        return generate_draft_with_retrieval(
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
        raise _service_unavailable() from exc


@router.post("/v1/tasks/generate-draft", response_model=EnqueueIngestResponse)
def enqueue_generate_draft(payload: DraftGenerationRequest) -> EnqueueIngestResponse:
    blocked, reasons = detect_pricing_content(payload.requirement_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    task = generate_draft_task.delay(
        payload.requirement_id,
        payload.requirement_text,
        payload.top_k,
        payload.project_id,
        payload.industry_tag,
        payload.tender_template_id,
    )
    return EnqueueIngestResponse(task_id=task.id, status="PENDING")


@router.post("/v1/workflow/section", response_model=WorkflowSectionResponse)
def enqueue_section_workflow(payload: WorkflowSectionRequest) -> WorkflowSectionResponse:
    outline_status = get_outline_status(payload.outline_id)
    if outline_status is None:
        raise HTTPException(status_code=404, detail="outline not found")
    if outline_status != "OUTLINE_CONFIRMED":
        raise HTTPException(status_code=400, detail="outline not confirmed")

    req_text = "。".join(payload.requirement_texts)
    blocked, reasons = detect_pricing_content(req_text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    extract_task = requirement_extract_task.delay(req_text)
    generate_task = section_generate_task.delay(
        payload.project_id,
        payload.section_key,
        req_text,
        payload.industry_tag,
    )
    validate_task = section_validate_task.delay("", [], [])
    render_task = render_export_task.delay([])
    mark_section_pending(payload.outline_id, payload.section_key)

    return WorkflowSectionResponse(
        section_key=payload.section_key,
        status="PENDING",
        task_ids={
            "REQUIREMENT_EXTRACT": extract_task.id,
            "SECTION_GENERATE": generate_task.id,
            "SECTION_VALIDATE": validate_task.id,
            "RENDER_EXPORT": render_task.id,
        },
    )


@router.post("/v1/workflow/section/confirm", response_model=SectionConfirmResponse)
def confirm_section(payload: SectionConfirmRequest) -> SectionConfirmResponse:
    try:
        status = confirm_section_run(payload.outline_id, payload.section_key, payload.approved)
        return SectionConfirmResponse(
            outline_id=payload.outline_id,
            section_key=payload.section_key,
            status=status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/v1/evidence/upsert", response_model=EnqueueIngestResponse)
def evidence_upsert(payload: EvidenceUpsertRequest) -> EnqueueIngestResponse:
    try:
        task = upsert_evidence_task.delay(payload.expert_doc_id, [item.model_dump() for item in payload.chunks])
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc


@router.post("/v1/evidence/extract-upsert", response_model=EnqueueIngestResponse)
def evidence_extract_upsert(payload: HistoricalExtractRequest) -> EnqueueIngestResponse:
    try:
        task = extract_upsert_historical_task.delay(payload.expert_doc_id, payload.text, payload.industry_tag)
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc


@router.post("/v1/evidence/feedback-upsert", response_model=EnqueueIngestResponse)
def feedback_upsert_section(payload: SectionFeedbackUpsertRequest) -> EnqueueIngestResponse:
    section_status = get_section_status(payload.outline_id, payload.section_key)
    if section_status != "SECTION_CONFIRMED":
        raise HTTPException(status_code=400, detail="section not confirmed")

    blocked, reasons = detect_pricing_content(payload.content_md)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    chunks = standardize_section_feedback_chunks(
        outline_id=payload.outline_id,
        section_key=payload.section_key,
        section_title=payload.section_title,
        content_md=payload.content_md,
        industry_tag=payload.industry_tag,
    )
    task = upsert_evidence_task.delay(payload.expert_doc_id, [item.model_dump() for item in chunks])
    return EnqueueIngestResponse(task_id=task.id, status="PENDING")


@router.post("/v1/evidence/search", response_model=EvidenceSearchResponse)
def evidence_search(payload: EvidenceSearchRequest) -> EvidenceSearchResponse:
    try:
        store = QdrantStore()
        hits = store.search(query=payload.query, top_k=payload.top_k, industry_tag=payload.industry_tag)
        return EvidenceSearchResponse(hits=to_search_hits(hits))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc


@router.post("/v1/cache/invalidate", response_model=PricingFuseResponse)
def cache_invalidate(prefix: str | None = None) -> PricingFuseResponse:
    count = invalidate_cache(prefix=prefix)
    return PricingFuseResponse(blocked=False, reasons=[f"invalidated={count}"])


@router.post("/v1/render/word", response_model=RenderWordResponse)
def render_doc(payload: RenderWordRequest) -> RenderWordResponse:
    output = render_word(
        output_path=payload.output_path,
        placeholders=payload.placeholders,
        template_path=payload.template_path,
    )
    return RenderWordResponse(output_path=output)
