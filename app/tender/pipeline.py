"""12-step state machine orchestrator for tender v1.1 import pipeline.

Steps:
  RECEIVED → UNPACKED → VALIDATED → SECTIONIZED → PRELIM_EXTRACTED →
  FATAL_GATE_CHECKED → SCORING_EXTRACTED → TECH_EXTRACTED →
  DEVIATION_BUILT → FORMAT_SIGNATURE_EXTRACTED → BLUEPRINT_BUILT →
  READY_FOR_WRITING

Branch: FATAL_GATE_CHECKED may → FATAL_BLOCKED (terminal)
Any step may → FAILED (terminal)
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from time import perf_counter

from app.db.session import session_scope
from app.models.tables import TenderImportRun, TenderRunStep
from app.tender.schemas import ImportReport, StepReport

logger = logging.getLogger(__name__)

# Ordered list of steps (index determines execution order)
_STEP_ORDER: list[TenderRunStep] = [
    TenderRunStep.RECEIVED,
    TenderRunStep.UNPACKED,
    TenderRunStep.VALIDATED,
    TenderRunStep.SECTIONIZED,
    TenderRunStep.PRELIM_EXTRACTED,
    TenderRunStep.FATAL_GATE_CHECKED,
    TenderRunStep.SCORING_EXTRACTED,
    TenderRunStep.TECH_EXTRACTED,
    TenderRunStep.DEVIATION_BUILT,
    TenderRunStep.FORMAT_SIGNATURE_EXTRACTED,
    TenderRunStep.BLUEPRINT_BUILT,
    TenderRunStep.READY_FOR_WRITING,
]


def _step_index(step: TenderRunStep) -> int:
    try:
        return _STEP_ORDER.index(step)
    except ValueError:
        return -1


def _update_step(run_id: uuid.UUID, step: TenderRunStep, error: str | None = None,
                 fatal_reason: dict | None = None) -> None:
    with session_scope() as db:
        run = db.get(TenderImportRun, run_id)
        if not run:
            raise ValueError(f"run {run_id} not found")
        run.current_step = step
        if error:
            run.error_detail = error[:2000]
        if fatal_reason:
            run.fatal_blocked_reason = fatal_reason
        db.commit()


def _save_derived(workspace: Path, filename: str, data: dict | list) -> None:
    derived_dir = workspace / "derived"
    derived_dir.mkdir(parents=True, exist_ok=True)
    (derived_dir / filename).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_pipeline(run_id: str) -> dict:
    """Execute the full tender import pipeline. Supports resume from current_step."""
    rid = uuid.UUID(run_id)

    # Load run
    with session_scope() as db:
        run = db.get(TenderImportRun, rid)
        if not run:
            raise ValueError(f"run {run_id} not found")
        current = run.current_step
        workspace = Path(run.workspace_path)
        tender_id = run.tender_id
        filename = run.filename

    # Determine resume point
    resume_idx = _step_index(current)
    if current in (TenderRunStep.FATAL_BLOCKED, TenderRunStep.FAILED):
        return {"run_id": run_id, "status": current.value, "message": "terminal state, cannot resume"}

    step_reports: list[StepReport] = []

    # ── Step 1: UNPACKED (already done during upload, mark complete) ──
    if resume_idx <= _step_index(TenderRunStep.UNPACKED):
        t0 = perf_counter()
        _update_step(rid, TenderRunStep.UNPACKED)
        step_reports.append(StepReport(step="UNPACKED", status="OK", duration_ms=int((perf_counter() - t0) * 1000)))

    # ── Step 2: VALIDATED ──
    if resume_idx <= _step_index(TenderRunStep.VALIDATED):
        t0 = perf_counter()
        try:
            from app.tender.zip_package import load_manifest, validate_tender_package
            manifest = load_manifest(workspace)
            warnings = validate_tender_package(workspace, manifest)
            _update_step(rid, TenderRunStep.VALIDATED)
            step_reports.append(StepReport(
                step="VALIDATED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"warnings: {warnings}" if warnings else None,
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 3: SECTIONIZED ──
    if resume_idx <= _step_index(TenderRunStep.SECTIONIZED):
        t0 = perf_counter()
        try:
            from app.tender.zip_package import read_full_markdown
            from app.tender.sectionizer import sectionize
            md_text = read_full_markdown(workspace)
            sections = sectionize(md_text)
            _save_derived(workspace, "tender_sections.json", sections.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.SECTIONIZED)
            step_reports.append(StepReport(
                step="SECTIONIZED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"{len(sections.sections)} sections",
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 4: PRELIM_EXTRACTED ──
    if resume_idx <= _step_index(TenderRunStep.PRELIM_EXTRACTED):
        t0 = perf_counter()
        try:
            from app.tender.prelim_extractor import extract_preliminary
            from app.tender.zip_package import read_full_markdown
            md_text = read_full_markdown(workspace)
            prelim = extract_preliminary(md_text)
            _save_derived(workspace, "preliminary_evaluation.json", prelim.model_dump(mode="json"))

            from app.tender.key_personnel_extractor import extract_key_personnel
            personnel = extract_key_personnel(md_text)
            _save_derived(workspace, "key_personnel_constraints.json", personnel.model_dump(mode="json"))

            _update_step(rid, TenderRunStep.PRELIM_EXTRACTED)
            step_reports.append(StepReport(
                step="PRELIM_EXTRACTED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"{prelim.fatal_count} fatal items, {len(personnel.constraints)} personnel constraints",
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 5: FATAL_GATE_CHECKED (R0 enforcement) ──
    if resume_idx <= _step_index(TenderRunStep.FATAL_GATE_CHECKED):
        t0 = perf_counter()
        try:
            from app.tender.fatal_gate import check_fatal_gate
            # Load prelim from derived
            prelim_path = workspace / "derived" / "preliminary_evaluation.json"
            prelim_data = json.loads(prelim_path.read_text(encoding="utf-8")) if prelim_path.exists() else {"items": []}
            personnel_path = workspace / "derived" / "key_personnel_constraints.json"
            personnel_data = json.loads(personnel_path.read_text(encoding="utf-8")) if personnel_path.exists() else {"constraints": []}

            gate_report = check_fatal_gate(prelim_data, personnel_data)
            _save_derived(workspace, "fatal_gate_report.json", gate_report.model_dump(mode="json"))

            if not gate_report.passed:
                # R0: FATAL_BLOCKED — stop all downstream
                _update_step(rid, TenderRunStep.FATAL_BLOCKED,
                             fatal_reason={"reasons": gate_report.blocked_reasons})
                step_reports.append(StepReport(
                    step="FATAL_GATE_CHECKED", status="FATAL_BLOCKED",
                    duration_ms=int((perf_counter() - t0) * 1000),
                    detail="; ".join(gate_report.blocked_reasons),
                ))
                # Save report and exit
                _save_import_report(workspace, tender_id, filename, step_reports, "FATAL_BLOCKED", fatal_blocked=True)
                return {"run_id": run_id, "status": "FATAL_BLOCKED", "reasons": gate_report.blocked_reasons}

            _update_step(rid, TenderRunStep.FATAL_GATE_CHECKED)
            step_reports.append(StepReport(
                step="FATAL_GATE_CHECKED", status="PASSED",
                duration_ms=int((perf_counter() - t0) * 1000),
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 6: SCORING_EXTRACTED ──
    if resume_idx <= _step_index(TenderRunStep.SCORING_EXTRACTED):
        t0 = perf_counter()
        try:
            from app.tender.scoring_extractor import extract_scoring
            from app.tender.zip_package import read_full_markdown
            md_text = read_full_markdown(workspace)
            scoring = extract_scoring(md_text)
            _save_derived(workspace, "scoring_model.json", scoring.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.SCORING_EXTRACTED)
            step_reports.append(StepReport(
                step="SCORING_EXTRACTED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"{len(scoring.items)} scoring items",
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 7: TECH_EXTRACTED ──
    if resume_idx <= _step_index(TenderRunStep.TECH_EXTRACTED):
        t0 = perf_counter()
        try:
            from app.tender.technical_extractor import extract_technical
            from app.tender.zip_package import read_full_markdown
            md_text = read_full_markdown(workspace)
            tech = extract_technical(md_text)
            _save_derived(workspace, "technical_requirements.json", tech.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.TECH_EXTRACTED)
            step_reports.append(StepReport(
                step="TECH_EXTRACTED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"{len(tech.requirements)} technical requirements",
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 8: DEVIATION_BUILT (R2) ──
    if resume_idx <= _step_index(TenderRunStep.DEVIATION_BUILT):
        t0 = perf_counter()
        try:
            from app.tender.deviation_builder import build_deviation_tables
            tech_path = workspace / "derived" / "technical_requirements.json"
            tech_data = json.loads(tech_path.read_text(encoding="utf-8")) if tech_path.exists() else {"requirements": []}
            deviations = build_deviation_tables(tech_data)
            _save_derived(workspace, "deviation_tables.json", deviations.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.DEVIATION_BUILT)
            step_reports.append(StepReport(
                step="DEVIATION_BUILT", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 9: FORMAT_SIGNATURE_EXTRACTED (R1) ──
    if resume_idx <= _step_index(TenderRunStep.FORMAT_SIGNATURE_EXTRACTED):
        t0 = perf_counter()
        try:
            from app.tender.format_signature_extractor import extract_format_signature
            from app.tender.zip_package import read_full_markdown
            md_text = read_full_markdown(workspace)
            fmt = extract_format_signature(md_text)
            _save_derived(workspace, "format_signature_constraints.json", fmt.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.FORMAT_SIGNATURE_EXTRACTED)
            step_reports.append(StepReport(
                step="FORMAT_SIGNATURE_EXTRACTED", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 10: BLUEPRINT_BUILT ──
    if resume_idx <= _step_index(TenderRunStep.BLUEPRINT_BUILT):
        t0 = perf_counter()
        try:
            from app.tender.blueprint_builder import build_blueprint
            # Load all derived data
            derived_dir = workspace / "derived"
            manifest = json.loads((workspace / "manifest.json").read_text(encoding="utf-8"))

            blueprint = build_blueprint(
                tender_id=tender_id,
                manifest=manifest,
                derived_dir=derived_dir,
            )
            _save_derived(workspace, "bid_blueprint.json", blueprint.model_dump(mode="json"))
            _update_step(rid, TenderRunStep.BLUEPRINT_BUILT)
            step_reports.append(StepReport(
                step="BLUEPRINT_BUILT", status="OK",
                duration_ms=int((perf_counter() - t0) * 1000),
                detail=f"{len(blueprint.tasks)} tasks",
            ))
        except Exception as exc:
            _update_step(rid, TenderRunStep.FAILED, error=str(exc))
            return {"run_id": run_id, "status": "FAILED", "error": str(exc)}

    # ── Step 11: Compliance check (combined) ──
    try:
        from app.tender.compliance_extractor import extract_compliance
        from app.tender.zip_package import read_full_markdown
        md_text = read_full_markdown(workspace)
        compliance = extract_compliance(md_text)
        _save_derived(workspace, "compliance_check.json", compliance.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("compliance extraction failed (non-fatal): %s", exc)

    # ── Step 12: READY_FOR_WRITING ──
    # R2 check: deviation_tables.json must exist before marking ready
    deviation_path = workspace / "derived" / "deviation_tables.json"
    if not deviation_path.exists():
        _update_step(rid, TenderRunStep.FAILED, error="deviation_tables.json missing — R2 violated")
        return {"run_id": run_id, "status": "FAILED", "error": "R2: deviation tables required before writing"}

    _update_step(rid, TenderRunStep.READY_FOR_WRITING)
    _save_import_report(workspace, tender_id, filename, step_reports, "READY_FOR_WRITING")

    return {"run_id": run_id, "status": "READY_FOR_WRITING"}


def _save_import_report(
    workspace: Path,
    tender_id: str,
    filename: str,
    step_reports: list[StepReport],
    final_status: str,
    *,
    fatal_blocked: bool = False,
) -> None:
    derived_dir = workspace / "derived"
    derived_files = sorted(f.name for f in derived_dir.iterdir() if f.is_file()) if derived_dir.is_dir() else []

    report = ImportReport(
        tender_id=tender_id,
        filename=filename,
        steps=step_reports,
        final_status=final_status,
        fatal_blocked=fatal_blocked,
        derived_files=derived_files,
    )
    _save_derived(workspace, "import_report.json", report.model_dump(mode="json"))
