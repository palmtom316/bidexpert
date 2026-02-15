from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator
from uuid import uuid4

from celery import chain
from celery.exceptions import CeleryError
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.schemas.contracts import (
    BatchIngestDirectoryRequest,
    BatchIngestDirectoryResponse,
    CompletedBidCreateRequest,
    CompletedBidDeleteResponse,
    CompletedBidItem,
    CompletedBidListResponse,
    DraftGenerationRequest,
    DraftGenerationResponse,
    EnqueueIngestResponse,
    ExpertLibraryChunkListResponse,
    ExpertLibraryDocListResponse,
    ExpertLibraryIngestResponse,
    ExpertLibraryStructuredIngestRequest,
    ExpertLibraryStructuredIngestResponse,
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
    ProjectModelPolicyResponse,
    ProjectModelPolicyUpsertRequest,
    PricingFuseRequest,
    PricingFuseResponse,
    ProviderProfileCreateRequest,
    ProviderProfileCreateResponse,
    ProviderProfileDeleteResponse,
    ProviderProfileItem,
    ProviderProfileListResponse,
    ProviderProfileTestResponse,
    SanitizeRequest,
    SanitizeResponse,
    SectionFeedbackUpsertRequest,
    RenderWordRequest,
    RenderWordResponse,
    SectionConfirmRequest,
    SectionConfirmResponse,
    TaskStatusResponse,
    TenderAnalyzeUploadResponse,
    TenderAnalysisDetailResponse,
    TenderAnalysisRunListResponse,
    WorkflowSectionRequest,
    WorkflowSectionResponse,
)
from app.services.byok import (
    create_provider_profile,
    delete_provider_profile,
    get_project_model_policy,
    list_provider_profiles,
    test_provider_profile,
    upsert_project_model_policy,
)
from app.services.completed_bids import create_completed_bid, delete_completed_bid, list_completed_bids
from app.services.evidence_validator import run_three_gates
from app.services.expert_library import (
    ingest_historical_pdf,
    ingest_structured_expert_knowledge,
    list_expert_chunks,
    list_expert_docs,
)
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.pdf_ingest import ingest_pdf_bytes
from app.services.pii_policy import sanitize_outbound_text
from app.services.pricing_guard import detect_pricing_content
from app.services.qdrant_store import QdrantStore, to_search_hits
from app.services.semantic_cache import invalidate_cache
from app.services.tender_analysis import (
    analyze_and_persist_tender_pdf,
    get_tender_analysis_detail,
    list_tender_analysis_runs,
)
from app.extract.tender_parser import parse_tender_requirements
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
from app.worker.tasks import (
    generate_draft_task,
    get_task_result,
    ingest_document_task,
    extract_upsert_historical_task,
    section_extract_stage_task,
    section_generate_stage_task,
    section_render_stage_task,
    section_validate_stage_task,
    upsert_evidence_task,
)

router = APIRouter()


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="service temporarily unavailable")


def _profile_to_item(profile) -> ProviderProfileItem:
    return ProviderProfileItem(
        id=str(profile.id),
        scope=str(profile.scope.value if hasattr(profile.scope, "value") else profile.scope),
        scope_id=str(profile.scope_id),
        provider=profile.provider,
        base_url=profile.base_url,
        default_model=profile.default_model,
        key_storage=str(profile.key_storage.value if hasattr(profile.key_storage, "value") else profile.key_storage),
        key_secret_ref=profile.key_secret_ref,
        allowed_tasks=profile.allowed_tasks or ["*"],
        created_by=profile.created_by,
    )


def _completed_bid_to_item(record) -> CompletedBidItem:
    return CompletedBidItem(
        id=str(record.id),
        project_id=record.project_id,
        project_name=record.project_name,
        engineering_category=record.engineering_category,
        tenderer=record.tenderer,
        bid_result=record.bid_result,
        file_name=record.file_name,
        file_info=record.file_info,
        completed_date=record.completed_date.isoformat() if record.completed_date else None,
        created_by=record.created_by,
        created_at=record.created_at.isoformat() if record.created_at else "",
    )


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/api/provider-profiles", response_model=ProviderProfileCreateResponse)
def create_provider_profile_api(payload: ProviderProfileCreateRequest) -> ProviderProfileCreateResponse:
    try:
        profile = create_provider_profile(
            project_id=payload.project_id,
            provider=payload.provider,
            base_url=payload.base_url,
            default_model=payload.default_model,
            api_key=payload.api_key,
            key_storage=payload.key_storage,
            allowed_tasks=payload.allowed_tasks,
        )
        return ProviderProfileCreateResponse(
            profile_id=str(profile.id),
            key_storage=str(profile.key_storage.value),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/provider-profiles", response_model=ProviderProfileListResponse)
def list_provider_profiles_api(project_id: str) -> ProviderProfileListResponse:
    try:
        items = [_profile_to_item(item) for item in list_provider_profiles(project_id)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProviderProfileListResponse(items=items)


@router.post("/api/provider-profiles/{profile_id}/test", response_model=ProviderProfileTestResponse)
def test_provider_profile_api(profile_id: str) -> ProviderProfileTestResponse:
    try:
        profile, ok, detail = test_provider_profile(profile_id)
        return ProviderProfileTestResponse(
            profile_id=str(profile.id),
            ok=ok,
            provider=profile.provider,
            model=profile.default_model,
            detail=detail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/api/provider-profiles/{profile_id}", response_model=ProviderProfileDeleteResponse)
def delete_provider_profile_api(profile_id: str) -> ProviderProfileDeleteResponse:
    try:
        deleted = delete_provider_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="provider profile not found")
    return ProviderProfileDeleteResponse(profile_id=profile_id, deleted=True)


@router.put("/api/projects/{project_id}/model-policy", response_model=ProjectModelPolicyResponse)
def put_model_policy_api(project_id: str, payload: ProjectModelPolicyUpsertRequest) -> ProjectModelPolicyResponse:
    try:
        policy = upsert_project_model_policy(
            project_id=project_id,
            extract_profile_id=payload.extract_profile_id,
            generate_profile_id=payload.generate_profile_id,
            review_profile_id=payload.review_profile_id,
            embed_profile_id=payload.embed_profile_id,
            query_rewrite_profile_id=payload.query_rewrite_profile_id,
            program_support_profile_id=payload.program_support_profile_id,
            enable_review=payload.enable_review,
            token_budget_total=payload.token_budget_total,
            concurrency_limits=payload.concurrency_limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProjectModelPolicyResponse(
        project_id=str(policy.project_id),
        extract_profile_id=str(policy.extract_profile_id) if policy.extract_profile_id else None,
        generate_profile_id=str(policy.generate_profile_id) if policy.generate_profile_id else None,
        review_profile_id=str(policy.review_profile_id) if policy.review_profile_id else None,
        embed_profile_id=str(policy.embed_profile_id) if policy.embed_profile_id else None,
        query_rewrite_profile_id=str(policy.query_rewrite_profile_id) if policy.query_rewrite_profile_id else None,
        program_support_profile_id=str(policy.program_support_profile_id) if policy.program_support_profile_id else None,
        enable_review=policy.enable_review,
        token_budget_total=int(policy.token_budget_total),
        token_budget_used=int(policy.token_budget_used),
        concurrency_limits=policy.concurrency_limits
        or {
            "extract": 2,
            "generate": 3,
            "review": 2,
            "embed": 2,
            "query_rewrite": 2,
            "program_support": 1,
        },
    )


@router.get("/api/projects/{project_id}/model-policy", response_model=ProjectModelPolicyResponse)
def get_model_policy_api(project_id: str) -> ProjectModelPolicyResponse:
    try:
        policy = get_project_model_policy(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not policy:
        raise HTTPException(status_code=404, detail="model policy not found")

    return ProjectModelPolicyResponse(
        project_id=str(policy.project_id),
        extract_profile_id=str(policy.extract_profile_id) if policy.extract_profile_id else None,
        generate_profile_id=str(policy.generate_profile_id) if policy.generate_profile_id else None,
        review_profile_id=str(policy.review_profile_id) if policy.review_profile_id else None,
        embed_profile_id=str(policy.embed_profile_id) if policy.embed_profile_id else None,
        query_rewrite_profile_id=str(policy.query_rewrite_profile_id) if policy.query_rewrite_profile_id else None,
        program_support_profile_id=str(policy.program_support_profile_id) if policy.program_support_profile_id else None,
        enable_review=policy.enable_review,
        token_budget_total=int(policy.token_budget_total),
        token_budget_used=int(policy.token_budget_used),
        concurrency_limits=policy.concurrency_limits
        or {
            "extract": 2,
            "generate": 3,
            "review": 2,
            "embed": 2,
            "query_rewrite": 2,
            "program_support": 1,
        },
    )


@router.post("/api/completed-bids", response_model=CompletedBidItem)
def create_completed_bid_api(payload: CompletedBidCreateRequest) -> CompletedBidItem:
    try:
        record = create_completed_bid(
            project_id=payload.project_id,
            project_name=payload.project_name,
            engineering_category=payload.engineering_category,
            tenderer=payload.tenderer,
            bid_result=payload.bid_result,
            file_name=payload.file_name,
            file_info=payload.file_info,
            completed_date=payload.completed_date,
            created_by=payload.created_by,
        )
        return _completed_bid_to_item(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


@router.get("/api/completed-bids", response_model=CompletedBidListResponse)
def list_completed_bids_api(project_id: str | None = None, limit: int = 200) -> CompletedBidListResponse:
    try:
        records = list_completed_bids(project_id=project_id, limit=limit)
        return CompletedBidListResponse(items=[_completed_bid_to_item(item) for item in records])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


@router.delete("/api/completed-bids/{record_id}", response_model=CompletedBidDeleteResponse)
def delete_completed_bid_api(record_id: str) -> CompletedBidDeleteResponse:
    try:
        deleted = delete_completed_bid(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="completed bid record not found")
    return CompletedBidDeleteResponse(record_id=record_id, deleted=True)


@router.post("/v1/tender/parse", response_model=ParseTenderResponse)
def parse_tender(payload: ParseTenderRequest) -> ParseTenderResponse:
    blocked, reasons = detect_pricing_content(payload.text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    parsed = parse_tender_requirements(payload.text)
    return ParseTenderResponse(requirements=parsed.requirements, status=parsed.status)


@router.post("/v1/tender/analyze-upload", response_model=TenderAnalyzeUploadResponse)
async def analyze_tender_upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    created_by: str = Form(default="system"),
) -> TenderAnalyzeUploadResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported")
    try:
        run, summary = analyze_and_persist_tender_pdf(
            filename=filename,
            content=await file.read(),
            project_id=project_id,
            created_by=created_by,
        )
        return TenderAnalyzeUploadResponse(
            run_id=run.run_id,
            project_id=run.project_id,
            document_id=run.document_id,
            filename=run.filename,
            status=run.status,
            summary=summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise _service_unavailable() from exc


@router.get("/v1/tender/analysis-runs", response_model=TenderAnalysisRunListResponse)
def list_tender_analysis_runs_api(project_id: str | None = None, limit: int = 50) -> TenderAnalysisRunListResponse:
    try:
        items = list_tender_analysis_runs(project_id=project_id, limit=limit)
        return TenderAnalysisRunListResponse(items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


@router.get("/v1/tender/analysis-runs/{run_id}", response_model=TenderAnalysisDetailResponse)
def get_tender_analysis_detail_api(run_id: str) -> TenderAnalysisDetailResponse:
    try:
        return get_tender_analysis_detail(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


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
    async def events() -> AsyncGenerator[str, None]:
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

    try:
        stage_chain = chain(
            section_extract_stage_task.s(
                payload.project_id,
                payload.section_key,
                req_text,
                payload.industry_tag,
            ),
            section_generate_stage_task.s(),
            section_validate_stage_task.s(),
            section_render_stage_task.s(),
        )
        pipeline_task = stage_chain.apply_async()
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc
    mark_section_pending(payload.outline_id, payload.section_key)

    return WorkflowSectionResponse(
        section_key=payload.section_key,
        status="PENDING",
        task_ids={
            "SECTION_PIPELINE": pipeline_task.id,
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
        task = extract_upsert_historical_task.delay(
            payload.expert_doc_id,
            payload.text,
            payload.industry_tag,
            (payload.model_id or "").strip() or None,
        )
        return EnqueueIngestResponse(task_id=task.id, status="PENDING")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (CeleryError, RuntimeError, ConnectionError, TimeoutError, OSError) as exc:
        raise _service_unavailable() from exc


@router.post("/v1/expert-library/ingest-upload", response_model=ExpertLibraryIngestResponse)
async def expert_library_ingest_upload(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    industry_tag: str | None = Form(default=None),
    title: str | None = Form(default=None),
    created_by: str = Form(default="system"),
    doc_type: str = Form(default="EXPERT_HISTORY"),
    model_id: str | None = Form(default=None),
) -> ExpertLibraryIngestResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported")
    try:
        return ingest_historical_pdf(
            filename=filename,
            content=await file.read(),
            project_id=project_id,
            industry_tag=industry_tag,
            title=title,
            created_by=created_by,
            doc_type=doc_type,
            model_id=(model_id or "").strip() or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise _service_unavailable() from exc


@router.post("/v1/expert-library/ingest-structured", response_model=ExpertLibraryStructuredIngestResponse)
def expert_library_ingest_structured(
    payload: ExpertLibraryStructuredIngestRequest,
) -> ExpertLibraryStructuredIngestResponse:
    try:
        return ingest_structured_expert_knowledge(
            project_id=payload.project_id,
            industry_tag=payload.industry_tag,
            created_by=payload.created_by,
            standard_items=payload.standard_items,
            company_performance_items=payload.company_performance_items,
            company_qualification_items=payload.company_qualification_items,
            pm_qualification_performance_items=payload.pm_qualification_performance_items,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


@router.get("/v1/expert-library/docs", response_model=ExpertLibraryDocListResponse)
def expert_library_docs(
    project_id: str | None = None,
    industry_tag: str | None = None,
    limit: int = 50,
) -> ExpertLibraryDocListResponse:
    try:
        items = list_expert_docs(project_id=project_id, industry_tag=industry_tag, limit=limit)
        return ExpertLibraryDocListResponse(items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _service_unavailable() from exc


@router.get("/v1/expert-library/docs/{expert_doc_id}/chunks", response_model=ExpertLibraryChunkListResponse)
def expert_library_doc_chunks(expert_doc_id: str, limit: int = 200) -> ExpertLibraryChunkListResponse:
    try:
        items = list_expert_chunks(expert_doc_id=expert_doc_id, limit=limit)
        return ExpertLibraryChunkListResponse(expert_doc_id=expert_doc_id, items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
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
    try:
        output = render_word(
            output_path=payload.output_path,
            placeholders=payload.placeholders,
            template_path=payload.template_path,
        )
        return RenderWordResponse(output_path=output)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
