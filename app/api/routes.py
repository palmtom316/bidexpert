from __future__ import annotations

import hmac
from pathlib import Path

from celery import chain
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.api.endpoints.evidence import router as evidence_router
from app.api.endpoints.generation import router as generation_router
from app.api.endpoints.provider import router as provider_router
from app.api.endpoints.redline_v2 import router as redline_v2_router
from app.api.endpoints.render import router as render_router
from app.api.endpoints.scorecard_v2 import router as scorecard_v2_router
from app.api.endpoints.tasks import router as tasks_router
from app.api.endpoints.tender import router as tender_router
from app.api.endpoints.workflow import router as workflow_router
from app.api.endpoints.evidence import (
    cache_invalidate,
    evidence_extract_upsert,
    evidence_search,
    evidence_upsert,
    expert_library_convert_confirm,
    expert_library_convert_upload,
    expert_library_doc_chunks,
    expert_library_docs,
    expert_library_ingest_structured,
    expert_library_ingest_upload,
    expert_library_ingest_uploads,
    feedback_upsert_section,
)
from app.api.endpoints.generation import (
    enqueue_generate_draft,
    generate_draft,
    pricing_fuse,
    sanitize_text,
    validate_generation,
)
from app.api.endpoints.provider import (
    create_completed_bid_api,
    create_provider_profile_api,
    delete_completed_bid_api,
    delete_provider_profile_api,
    get_model_policy_api,
    list_audit_logs_api,
    list_completed_bids_api,
    list_provider_profiles_api,
    put_model_policy_api,
    qualify_provider_profile_api,
    test_ocr_connection_api,
    test_provider_connection_api,
    test_provider_profile_api,
)
from app.api.endpoints.render import render_doc, render_structured_doc
from app.api.endpoints.tasks import enqueue_ingest, enqueue_ingest_directory, task_status, task_status_stream
from app.api.endpoints.tender import (
    analyze_tender_upload,
    get_tender_analysis_detail_api,
    get_blueprint,
    get_derived_file,
    get_fatal_gate_report,
    get_import_report,
    get_import_run_detail,
    import_tender_zip,
    ingest_tender_upload,
    list_import_runs,
    list_tender_analysis_runs_api,
    parse_tender,
)
from app.api.endpoints.workflow import (
    calculate_score_api,
    calculate_score_v2_api,
    confirm_outline,
    confirm_section,
    create_outline,
    enqueue_section_workflow,
    review_full_api,
    review_section_api,
)
from app.core.config import settings
from app.extract.tender_parser import parse_tender_requirements
from app.schemas.contracts import HealthResponse
from app.security import AuthContext, decode_jwt, get_auth_context, set_auth_context
from app.services.byok import (
    create_provider_profile,
    delete_provider_profile,
    get_project_model_policy,
    list_provider_profiles,
    qualify_provider_profile,
    test_provider_connection,
    test_provider_profile,
    upsert_project_model_policy,
)
from app.services.audit_log import list_audit_logs, record_audit_event
from app.services.completed_bids import create_completed_bid, delete_completed_bid, list_completed_bids
from app.services.adapters.ocr import test_ocr_connection
from app.services.evidence_validator import run_three_gates
from app.services.expert_library import (
    confirm_structured_conversion_ingest,
    convert_upload_to_structured,
    ingest_historical_pdf,
    ingest_structured_expert_knowledge,
    list_expert_chunks,
    list_expert_docs,
)
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.knowledge_standardizer import standardize_section_feedback_chunks
from app.services.ingest.file_router import ingest_upload_request
from app.services.pdf_ingest import ingest_pdf_bytes
from app.services.pii_policy import sanitize_outbound_text
from app.services.pricing_guard import detect_pricing_content
from app.services.qdrant_store import get_qdrant_store, to_search_hits
from app.services.review_engine import run_compliance_review, run_full_compliance_review
from app.services.scoring_engine import run_scoring_service
from app.services.semantic_cache import invalidate_cache
from app.services.tender_analysis import (
    analyze_and_persist_tender_pdf,
    get_tender_analysis_detail,
    list_tender_analysis_runs,
)
from app.services.workflow_runs import (
    confirm_outline_run,
    confirm_section_run,
    create_outline_run,
    get_outline_status,
    get_resume_from_step,
    get_section_status,
    mark_section_pending,
    update_run_progress,
)
from app.services.word_renderer import render_word, render_word_structured
from app.worker.tasks import (
    extract_upsert_historical_task,
    generate_draft_task,
    get_task_result,
    ingest_document_task,
    section_extract_stage_task,
    section_generate_stage_task,
    section_render_stage_task,
    section_validate_stage_task,
    upsert_evidence_task,
)

__all__ = [
    "router",
    "_require_auth",
    "_resolved_created_by",
    "_resolve_within_base",
    "_read_upload_with_limit",
    "_service_unavailable",
    "create_provider_profile_api",
    "list_provider_profiles_api",
    "test_provider_connection_api",
    "test_ocr_connection_api",
    "test_provider_profile_api",
    "qualify_provider_profile_api",
    "delete_provider_profile_api",
    "put_model_policy_api",
    "get_model_policy_api",
    "create_completed_bid_api",
    "list_completed_bids_api",
    "delete_completed_bid_api",
    "list_audit_logs_api",
    "parse_tender",
    "analyze_tender_upload",
    "list_tender_analysis_runs_api",
    "get_tender_analysis_detail_api",
    "ingest_tender_upload",
    "import_tender_zip",
    "list_import_runs",
    "get_import_run_detail",
    "get_import_report",
    "get_blueprint",
    "get_fatal_gate_report",
    "get_derived_file",
    "enqueue_ingest",
    "enqueue_ingest_directory",
    "task_status",
    "task_status_stream",
    "pricing_fuse",
    "sanitize_text",
    "validate_generation",
    "generate_draft",
    "enqueue_generate_draft",
    "create_outline",
    "confirm_outline",
    "enqueue_section_workflow",
    "confirm_section",
    "review_section_api",
    "review_full_api",
    "calculate_score_api",
    "calculate_score_v2_api",
    "evidence_upsert",
    "evidence_extract_upsert",
    "expert_library_convert_upload",
    "expert_library_convert_confirm",
    "expert_library_ingest_upload",
    "expert_library_ingest_uploads",
    "expert_library_ingest_structured",
    "expert_library_docs",
    "expert_library_doc_chunks",
    "feedback_upsert_section",
    "evidence_search",
    "cache_invalidate",
    "render_doc",
    "render_structured_doc",
    "chain",
    "settings",
    "parse_tender_requirements",
    "create_provider_profile",
    "delete_provider_profile",
    "get_project_model_policy",
    "list_provider_profiles",
    "test_provider_connection",
    "qualify_provider_profile",
    "test_ocr_connection",
    "test_provider_profile",
    "upsert_project_model_policy",
    "record_audit_event",
    "list_audit_logs",
    "create_completed_bid",
    "delete_completed_bid",
    "list_completed_bids",
    "run_three_gates",
    "convert_upload_to_structured",
    "confirm_structured_conversion_ingest",
    "ingest_historical_pdf",
    "ingest_structured_expert_knowledge",
    "list_expert_chunks",
    "list_expert_docs",
    "generate_draft_with_retrieval",
    "standardize_section_feedback_chunks",
    "ingest_pdf_bytes",
    "ingest_upload_request",
    "sanitize_outbound_text",
    "detect_pricing_content",
    "get_qdrant_store",
    "to_search_hits",
    "run_compliance_review",
    "run_full_compliance_review",
    "run_scoring_service",
    "invalidate_cache",
    "analyze_and_persist_tender_pdf",
    "get_tender_analysis_detail",
    "list_tender_analysis_runs",
    "confirm_outline_run",
    "confirm_section_run",
    "create_outline_run",
    "get_outline_status",
    "get_resume_from_step",
    "get_section_status",
    "mark_section_pending",
    "update_run_progress",
    "render_word",
    "render_word_structured",
    "extract_upsert_historical_task",
    "generate_draft_task",
    "get_task_result",
    "ingest_document_task",
    "section_extract_stage_task",
    "section_generate_stage_task",
    "section_render_stage_task",
    "section_validate_stage_task",
    "upsert_evidence_task",
]

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_bearer_header = HTTPBearer(auto_error=False)


def _auth_mode() -> str:
    normalized = (settings.auth_mode or "api_key").strip().lower()
    return normalized if normalized in {"api_key", "jwt", "hybrid"} else "api_key"


def _configured_api_key() -> str | None:
    value = (settings.api_key or "").strip()
    return value or None


def validate_auth_configuration() -> None:
    mode = _auth_mode()
    if mode == "api_key" and _configured_api_key() is None:
        raise RuntimeError("BIDEXPERT_API_KEY is required when BIDEXPERT_AUTH_MODE=api_key")


def _resolved_created_by(provided: str | None) -> str:
    auth = get_auth_context()
    if auth.method == "jwt":
        return auth.user_id
    if auth.method == "api_key" and auth.user_id:
        return auth.user_id
    return "system"


async def _require_auth(
    key: str | None = Depends(_api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Depends(_bearer_header),
) -> None:
    mode = _auth_mode()
    set_auth_context(AuthContext(user_id="system", method="anonymous"))

    if mode in {"jwt", "hybrid"}:
        jwt_secret = (settings.jwt_secret or "").strip() or None
        jwt_public_key = (settings.jwt_public_key_pem or "").strip() or None
        if bearer:
            if bearer.scheme.lower() != "bearer":
                raise HTTPException(status_code=401, detail="invalid authorization scheme")
            try:
                claims = decode_jwt(
                    bearer.credentials,
                    secret=jwt_secret,
                    public_key_pem=jwt_public_key,
                    allowed_algorithms=settings.jwt_allowed_algorithms,
                    expected_issuer=(settings.jwt_issuer or "").strip() or None,
                    expected_audience=(settings.jwt_audience or "").strip() or None,
                )
            except ValueError as exc:
                raise HTTPException(status_code=401, detail=f"invalid bearer token: {exc}") from exc
            subject = str(claims.get("sub", "")).strip()
            if not subject:
                raise HTTPException(status_code=401, detail="jwt subject is required")
            set_auth_context(AuthContext(user_id=subject, method="jwt"))
            return
        if mode == "jwt":
            raise HTTPException(status_code=401, detail="missing bearer token")

    if mode in {"api_key", "hybrid"}:
        expected = _configured_api_key()
        if not expected:
            raise HTTPException(status_code=401, detail="api key authentication is not configured")
        secondary = (settings.api_key_secondary or "").strip() or None
        if key and (hmac.compare_digest(key, expected) or (secondary and hmac.compare_digest(key, secondary))):
            set_auth_context(AuthContext(user_id="api-key-user", method="api_key"))
            return
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    raise HTTPException(status_code=401, detail="authentication required")


def _service_unavailable() -> HTTPException:
    return HTTPException(status_code=503, detail="service temporarily unavailable")


def _resolve_within_base(
    user_path: str,
    base_dir: Path,
    *,
    require_exists: bool = False,
    require_directory: bool = False,
) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    resolved_base = base_dir.resolve()
    candidate = Path(user_path)
    target = candidate if candidate.is_absolute() else (resolved_base / candidate)
    resolved_target = target.resolve(strict=False)

    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="path traversal detected") from exc

    if require_exists and not resolved_target.exists():
        raise HTTPException(status_code=400, detail="path not found")
    if require_directory and not resolved_target.is_dir():
        raise HTTPException(status_code=400, detail="path is not a directory")
    return resolved_target


async def _read_upload_with_limit(file: UploadFile) -> bytes:
    limit = int(settings.max_upload_bytes)
    content_length = file.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(
                    status_code=413,
                    detail=f"file exceeds max_upload_bytes={settings.max_upload_bytes}",
                )
        except ValueError:
            pass

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(min(1024 * 1024, max(1, limit - total + 1)))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status_code=413,
                detail=f"file exceeds max_upload_bytes={settings.max_upload_bytes}",
            )
        chunks.append(chunk)
    return b"".join(chunks)


router = APIRouter(dependencies=[Depends(_require_auth)])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


router.include_router(provider_router)
router.include_router(tender_router)
router.include_router(redline_v2_router)
router.include_router(scorecard_v2_router)
router.include_router(tasks_router)
router.include_router(generation_router)
router.include_router(workflow_router)
router.include_router(evidence_router)
router.include_router(render_router)
