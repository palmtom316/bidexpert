from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.core.config import settings
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
    TenderImportRunDetailResponse,
    TenderImportRunItem,
    TenderImportRunListResponse,
    TenderImportZipResponse,
)

_log = logging.getLogger(__name__)

router = APIRouter()


def _resolve_derived_file_path(workspace_path: str, filename: str) -> Path:
    workspace_root = Path(settings.tender_workspace_dir).resolve()
    workspace = Path(workspace_path).resolve()
    try:
        workspace.relative_to(workspace_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="workspace path is outside configured root") from exc

    derived_root = (workspace / "derived").resolve()
    file_path = (derived_root / filename).resolve()
    try:
        file_path.relative_to(derived_root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="derived file path escaped workspace boundary") from exc
    return file_path


def _ctx():
    from app.api import routes

    return routes


def _audit(action: str, *, actor: str = "system", project_id: str | None = None, target_id: str | None = None, meta: dict | None = None) -> None:
    try:
        from app.services.audit_log import record_audit_event
        record_audit_event(action=action, actor_user_id=actor, project_id=project_id, target_id=target_id, metadata=meta)
    except Exception:
        _log.warning("audit write failed for %s", action, exc_info=True)


# ── v1.0 endpoints (unchanged) ────────────────────────────────

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
    result = await analyze_tender_upload_handler(
        file=file,
        project_id=project_id,
        created_by=created_by,
        read_upload_with_limit_fn=ctx._read_upload_with_limit,
        analyze_and_persist_tender_pdf_fn=ctx.analyze_and_persist_tender_pdf,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
    _audit("tender.analyze_upload", actor=created_by, project_id=project_id, meta={"filename": file.filename})
    return result


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


# ── v1.1 endpoints (new) ──────────────────────────────────────

@router.post("/v1/tender/import-zip", response_model=TenderImportZipResponse)
async def import_tender_zip(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    created_by: str = Form(default="system"),
) -> TenderImportZipResponse:
    """Upload a .tender.zip, create an import run, enqueue the pipeline."""
    ctx = _ctx()
    content = await ctx._read_upload_with_limit(file)
    created_by = ctx._resolved_created_by(created_by)

    if not (file.filename or "").endswith(".zip"):
        raise HTTPException(status_code=400, detail="file must be a .tender.zip")

    from app.core.config import settings
    from app.db.session import session_scope
    from app.models.tables import TenderImportRun, TenderRunStep
    from app.tender.zip_package import TenderPackageError, load_manifest, unpack_zip, validate_tender_package

    run_id = uuid.uuid4()
    workspace = Path(settings.tender_workspace_dir) / str(run_id)

    try:
        root = unpack_zip(content, workspace)
        manifest = load_manifest(root)
        validate_tender_package(root, manifest)
    except TenderPackageError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    project_uuid = None
    if project_id:
        try:
            project_uuid = uuid.UUID(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid project_id") from exc

    with session_scope() as db:
        run = TenderImportRun(
            id=run_id,
            project_id=project_uuid,
            tender_id=manifest.tender_id,
            filename=file.filename or "unknown.zip",
            workspace_path=str(root),
            current_step=TenderRunStep.RECEIVED,
            created_by=created_by,
        )
        db.add(run)
        db.commit()

    from app.worker.tender_tasks import tender_import_pipeline_task

    tender_import_pipeline_task.delay(str(run_id))

    _audit("tender.import_zip", actor=created_by, project_id=project_id, target_id=str(run_id), meta={"filename": file.filename, "tender_id": manifest.tender_id})

    return TenderImportZipResponse(
        run_id=str(run_id),
        tender_id=manifest.tender_id,
        filename=file.filename or "unknown.zip",
        status="RECEIVED",
    )


@router.get("/v1/tender/import-runs", response_model=TenderImportRunListResponse)
def list_import_runs(project_id: str | None = None, limit: int = 50) -> TenderImportRunListResponse:
    """List tender import runs."""
    from app.db.session import session_scope
    from app.models.tables import TenderImportRun
    from sqlalchemy import select

    with session_scope() as db:
        stmt = select(TenderImportRun).order_by(TenderImportRun.created_at.desc()).limit(max(1, min(limit, 200)))
        if project_id:
            try:
                project_uuid = uuid.UUID(project_id)
                stmt = stmt.where(TenderImportRun.project_id == project_uuid)
            except ValueError:
                pass
        runs = db.execute(stmt).scalars().all()
        return TenderImportRunListResponse(
            items=[
                TenderImportRunItem(
                    run_id=str(r.id),
                    project_id=str(r.project_id) if r.project_id else None,
                    tender_id=r.tender_id,
                    filename=r.filename,
                    current_step=r.current_step.value if hasattr(r.current_step, "value") else str(r.current_step),
                    fatal_blocked_reason=r.fatal_blocked_reason,
                    error_detail=r.error_detail,
                    created_at=r.created_at.isoformat() if r.created_at else "",
                )
                for r in runs
            ]
        )


@router.get("/v1/tender/import-runs/{run_id}", response_model=TenderImportRunDetailResponse)
def get_import_run_detail(run_id: str) -> TenderImportRunDetailResponse:
    """Get import run detail with derived file list."""
    from app.db.session import session_scope
    from app.models.tables import TenderImportRun
    from sqlalchemy import select

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run_id") from exc

    with session_scope() as db:
        run = db.execute(select(TenderImportRun).where(TenderImportRun.id == run_uuid)).scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="import run not found")

        # List derived files from workspace
        derived: list[str] = []
        workspace = Path(run.workspace_path).resolve()
        workspace_root = Path(settings.tender_workspace_dir).resolve()
        try:
            workspace.relative_to(workspace_root)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="workspace path is outside configured root") from exc
        derived_dir = workspace / "derived"
        if derived_dir.is_dir():
            derived = sorted(f.name for f in derived_dir.iterdir() if f.is_file())

        return TenderImportRunDetailResponse(
            run=TenderImportRunItem(
                run_id=str(run.id),
                project_id=str(run.project_id) if run.project_id else None,
                tender_id=run.tender_id,
                filename=run.filename,
                current_step=run.current_step.value if hasattr(run.current_step, "value") else str(run.current_step),
                fatal_blocked_reason=run.fatal_blocked_reason,
                error_detail=run.error_detail,
                created_at=run.created_at.isoformat() if run.created_at else "",
            ),
            derived_files=derived,
        )


@router.get("/v1/tender/import-runs/{run_id}/report")
def get_import_report(run_id: str) -> FileResponse:
    """Download import_report.json for a run."""
    return _serve_derived_file(run_id, "import_report.json")


@router.get("/v1/tender/import-runs/{run_id}/blueprint")
def get_blueprint(run_id: str) -> FileResponse:
    """Download bid_blueprint.json for a run."""
    return _serve_derived_file(run_id, "bid_blueprint.json")


@router.get("/v1/tender/import-runs/{run_id}/fatal-gate-report")
def get_fatal_gate_report(run_id: str) -> FileResponse:
    """Download fatal_gate_report.json for a run."""
    return _serve_derived_file(run_id, "fatal_gate_report.json")


@router.get("/v1/tender/{tender_id}/derived/{name}")
def get_derived_file(tender_id: str, name: str) -> FileResponse:
    """Download any derived file (whitelist-checked)."""
    from app.tender.zip_package import is_allowed_derived_name

    if not is_allowed_derived_name(name):
        raise HTTPException(status_code=400, detail=f"derived file not allowed: {name}")

    from app.db.session import session_scope
    from app.models.tables import TenderImportRun
    from sqlalchemy import select

    with session_scope() as db:
        run = db.execute(
            select(TenderImportRun).where(TenderImportRun.tender_id == tender_id)
            .order_by(TenderImportRun.created_at.desc())
        ).scalars().first()
        if not run:
            raise HTTPException(status_code=404, detail="no import run found for tender_id")

        file_path = _resolve_derived_file_path(run.workspace_path, name)
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"derived file not found: {name}")
        return FileResponse(str(file_path), media_type="application/json", filename=name)


def _serve_derived_file(run_id: str, filename: str) -> FileResponse:
    """Helper to serve a derived file from a run's workspace."""
    from app.db.session import session_scope
    from app.models.tables import TenderImportRun
    from sqlalchemy import select

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid run_id") from exc

    with session_scope() as db:
        run = db.execute(select(TenderImportRun).where(TenderImportRun.id == run_uuid)).scalar_one_or_none()
        if not run:
            raise HTTPException(status_code=404, detail="import run not found")

        file_path = _resolve_derived_file_path(run.workspace_path, filename)
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"{filename} not yet generated")
        return FileResponse(str(file_path), media_type="application/json", filename=filename)
