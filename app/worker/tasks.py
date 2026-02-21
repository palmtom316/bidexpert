from __future__ import annotations

import logging
import re
from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult

from app.core.config import settings
from app.extract.historical_extractor import extract_evidence_chunks_from_text
from app.extract.tender_parser import parse_tender_requirements
from app.schemas.contracts import EvidenceUpsertItem
from app.services.evidence_validator import run_three_gates
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.global_facts import extract_global_facts_from_text
from app.services.pdf_ingest import ingest_pdf_bytes
from app.services.qdrant_store import get_qdrant_store
from app.services.workflow_artifacts import load_gate_artifact, persist_gate_artifact
from app.services.workflow_runs import update_run_progress
from app.services.word_renderer import render_word_structured
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _extract_stage(requirement_text: str) -> dict:
    parsed = parse_tender_requirements(requirement_text)
    return {
        "status": parsed.status,
        "requirements": [r.model_dump() for r in parsed.requirements],
    }


def _generate_stage(
    *,
    project_id: str,
    section_key: str,
    requirement_text: str,
    industry_tag: str | None,
    global_facts: dict | None,
    retries: int,
) -> dict:
    result = generate_draft_with_retrieval(
        requirement_id=section_key,
        requirement_text=requirement_text,
        top_k=settings.top_k_default,
        project_id=project_id,
        industry_tag=industry_tag,
        global_facts=global_facts,
        retry_count=retries,
        fallback_count=0,
    )
    return result.model_dump()


def _validate_stage(*, requirement_text: str, generated: dict) -> dict:
    gate_result = run_three_gates(
        generated_text=str(generated.get("generated_text", "")),
        evidence_ids=list(generated.get("evidence_ids", [])),
        evidence_texts=[],  # deterministic check already runs inside generation pipeline
        requirement_mapped=1 if generated.get("evidence_ids") else 0,
        requirement_total=1,
        coverage_threshold=settings.min_matrix_coverage,
        requirement_text=requirement_text,
    )
    return {
        "status": gate_result.status,
        "missing_sentences": gate_result.missing_sentences,
        "coverage": gate_result.coverage,
    }


def _safe_token(value: str | None, fallback: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(value or "").strip()).strip("._")
    return token or fallback


def _safe_update_run_progress(**kwargs) -> None:  # noqa: ANN003
    try:
        update_run_progress(**kwargs)
    except ValueError:
        return None


def _structured_content_from_generated(*, section_key: str, generated: dict) -> dict[str, list[dict[str, str]]]:
    section_title = f"章节 {section_key}"
    body: list[dict[str, str]] = [{"type": "heading", "style": "Title1", "text": section_title}]

    generation_json = generated.get("generation_json")
    content_blocks = generation_json.get("content_blocks") if isinstance(generation_json, dict) else None
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text", "")).strip()
            if not text:
                continue
            body.append({"type": "paragraph", "style": "BodyText", "text": text})

    if len(body) == 1:
        generated_text = str(generated.get("generated_text", "")).strip()
        if generated_text:
            for paragraph in [line.strip() for line in generated_text.splitlines() if line.strip()]:
                body.append({"type": "paragraph", "style": "BodyText", "text": paragraph})

    if len(body) == 1:
        body.append({"type": "paragraph", "style": "BodyText", "text": "NEED_HUMAN_INPUT"})

    return {"body": body, "appendix": []}


def _render_stage(*, context: dict, generated: dict) -> dict:
    final_status = str(generated.get("status", "NEED_HUMAN_INPUT"))
    render_ready = final_status == "SUPPORTED"
    if not render_ready:
        return {
            "status": "NEED_HUMAN_INPUT",
            "render_ready": False,
            "output_path": None,
            "pdf_path": None,
        }

    project_token = _safe_token(str(context.get("project_id", "")), "project")
    section_token = _safe_token(str(context.get("section_key", "")), "section")
    output_path = f"workflow/{project_token}/{section_token}-{uuid4().hex[:8]}.docx"

    try:
        rendered_docx, rendered_pdf = render_word_structured(
            output_path=output_path,
            content=_structured_content_from_generated(section_key=section_token, generated=generated),
            placeholders={"project_name": project_token, "section_key": section_token},
            template_path=None,
            style_config={},
            export_pdf=False,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        logger.exception("section render failed for section_key=%s", context.get("section_key"))
        return {
            "status": "FAILED",
            "render_ready": False,
            "output_path": None,
            "pdf_path": None,
            "error": str(exc),
        }

    return {
        "status": "SUCCEEDED",
        "render_ready": True,
        "output_path": rendered_docx,
        "pdf_path": rendered_pdf,
    }


@celery_app.task(bind=True, name="tasks.ingest_document", max_retries=settings.task_max_retries)
def ingest_document_task(self, file_path: str) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "LOAD_FILE"})
    path = Path(file_path)
    if not path.exists():
        return {"status": "FAILED", "error": f"file not found: {file_path}"}

    self.update_state(state="PROGRESS", meta={"stage": "INGEST_PDF"})
    result = ingest_pdf_bytes(path.name, path.read_bytes(), enable_ocr_fallback=settings.enable_ocr_fallback)
    return result.model_dump()


@celery_app.task(bind=True, name="tasks.requirement_extract", max_retries=settings.task_max_retries)
def requirement_extract_task(self, tender_text: str) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "REQUIREMENT_EXTRACT"})
    return _extract_stage(tender_text)


@celery_app.task(bind=True, name="tasks.section_generate", max_retries=settings.task_max_retries)
def section_generate_task(
    self,
    project_id: str,
    section_key: str,
    requirement_text: str,
    industry_tag: str | None = None,
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "SECTION_GENERATE"})
    return _generate_stage(
        project_id=project_id,
        section_key=section_key,
        requirement_text=requirement_text,
        industry_tag=industry_tag,
        retries=int(getattr(self.request, "retries", 0)),
    )


@celery_app.task(bind=True, name="tasks.section_validate", max_retries=settings.task_max_retries)
def section_validate_task(
    self,
    generated_text: str,
    evidence_ids: list[str],
    evidence_texts: list[str],
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "SECTION_VALIDATE"})
    gate_result = run_three_gates(
        generated_text=generated_text,
        evidence_ids=evidence_ids,
        evidence_texts=evidence_texts,
        requirement_mapped=1 if evidence_ids else 0,
        requirement_total=1,
        coverage_threshold=settings.min_matrix_coverage,
    )
    return {
        "status": gate_result.status,
        "missing_sentences": gate_result.missing_sentences,
        "coverage": gate_result.coverage,
    }


@celery_app.task(bind=True, name="tasks.render_export", max_retries=settings.task_max_retries)
def render_export_task(self, section_outputs: list[dict]) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "RENDER_EXPORT"})
    blocked = [x for x in section_outputs if x.get("status") != "SUPPORTED"]
    if blocked:
        return {"status": "NEED_HUMAN_INPUT", "blocked_sections": len(blocked)}
    return {"status": "SUCCEEDED", "rendered_sections": len(section_outputs)}


@celery_app.task(bind=True, name="tasks.upsert_evidence", max_retries=settings.task_max_retries)
def upsert_evidence_task(self, expert_doc_id: str, chunks: list[dict]) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "UPSERT_EVIDENCE"})
    store = get_qdrant_store()
    chunk_objs = [EvidenceUpsertItem(**chunk) for chunk in chunks]
    count = store.upsert_chunks(expert_doc_id=expert_doc_id, chunks=chunk_objs)
    return {"status": "SUCCEEDED", "upserted": count}


@celery_app.task(bind=True, name="tasks.extract_upsert_historical", max_retries=settings.task_max_retries)
def extract_upsert_historical_task(
    self,
    expert_doc_id: str,
    text: str,
    industry_tag: str | None = None,
    model_id: str | None = None,
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "EXTRACT_HISTORICAL"})
    store = get_qdrant_store()
    chunks = extract_evidence_chunks_from_text(
        text=text,
        industry_tag=industry_tag,
        model_id=model_id,
    )
    count = store.upsert_chunks(expert_doc_id=expert_doc_id, chunks=chunks)
    return {"status": "SUCCEEDED", "upserted": count}


@celery_app.task(bind=True, name="tasks.generate_draft", max_retries=settings.task_max_retries)
def generate_draft_task(
    self,
    requirement_id: str,
    requirement_text: str,
    top_k: int = 5,
    project_id: str | None = None,
    industry_tag: str | None = None,
    tender_template_id: str | None = None,
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "GENERATE_DRAFT"})
    result = generate_draft_with_retrieval(
        requirement_id=requirement_id,
        requirement_text=requirement_text,
        top_k=top_k,
        project_id=project_id,
        industry_tag=industry_tag,
        tender_template_id=tender_template_id,
        retry_count=int(getattr(self.request, "retries", 0)),
        fallback_count=0,
    )
    return result.model_dump()


@celery_app.task(bind=True, name="tasks.section_extract_stage", max_retries=settings.task_max_retries)
def section_extract_stage_task(
    self,
    outline_id: str,
    project_id: str,
    section_key: str,
    requirement_text: str,
    industry_tag: str | None = None,
    resume_from_step: str = "G1",
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "REQUIREMENT_EXTRACT"})
    try:
        extract_payload: dict
        global_facts: dict
        if resume_from_step in {"G2", "G3", "G4", "G5"}:
            cached = load_gate_artifact(outline_id=outline_id, section_key=section_key, gate="G1")
            if cached:
                extract_payload = dict(cached.get("extract") or {})
                global_facts = dict(cached.get("global_facts") or {})
            else:
                extract_payload = _extract_stage(requirement_text)
                global_facts = extract_global_facts_from_text(requirement_text)
        else:
            extract_payload = _extract_stage(requirement_text)
            global_facts = extract_global_facts_from_text(requirement_text)

        persist_gate_artifact(
            outline_id=outline_id,
            section_key=section_key,
            gate="G1",
            payload={
                "extract": extract_payload,
                "global_facts": global_facts,
            },
        )
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G1",
            step_status="parsing_done",
            resume_from_step="G2",
            last_error=None,
        )

        return {
            "outline_id": outline_id,
            "project_id": project_id,
            "section_key": section_key,
            "requirement_text": requirement_text,
            "industry_tag": industry_tag,
            "resume_from_step": resume_from_step,
            "global_facts": global_facts,
            "stages": {
                "extract": extract_payload,
            },
        }
    except Exception as exc:  # noqa: BLE001
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G1",
            step_status="failed",
            resume_from_step="G1",
            last_error=str(exc),
            retry_increment=1,
        )
        raise


@celery_app.task(bind=True, name="tasks.section_generate_stage", max_retries=settings.task_max_retries)
def section_generate_stage_task(self, context: dict) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "SECTION_GENERATE"})
    outline_id = str(context.get("outline_id", "") or "")
    section_key = str(context.get("section_key", "") or "")
    resume_from_step = str(context.get("resume_from_step", "G1") or "G1")
    try:
        cached = None
        if resume_from_step in {"G3", "G4", "G5"}:
            cached = load_gate_artifact(outline_id=outline_id, section_key=section_key, gate="G2")

        if cached:
            generated = cached
        else:
            generated = _generate_stage(
                project_id=str(context["project_id"]),
                section_key=section_key,
                requirement_text=str(context["requirement_text"]),
                industry_tag=context.get("industry_tag"),
                global_facts=context.get("global_facts") if isinstance(context.get("global_facts"), dict) else None,
                retries=int(getattr(self.request, "retries", 0)),
            )
            persist_gate_artifact(
                outline_id=outline_id,
                section_key=section_key,
                gate="G2",
                payload=generated,
            )

        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G2",
            step_status="generating",
            resume_from_step="G3",
            last_error=None,
        )
        context.setdefault("stages", {})["generate"] = generated
        context["status"] = generated.get("status", "NEED_HUMAN_INPUT")
        return context
    except Exception as exc:  # noqa: BLE001
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G2",
            step_status="failed",
            resume_from_step="G2",
            last_error=str(exc),
            retry_increment=1,
        )
        raise


@celery_app.task(bind=True, name="tasks.section_validate_stage", max_retries=settings.task_max_retries)
def section_validate_stage_task(self, context: dict) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "SECTION_VALIDATE"})
    outline_id = str(context.get("outline_id", "") or "")
    section_key = str(context.get("section_key", "") or "")
    resume_from_step = str(context.get("resume_from_step", "G1") or "G1")
    try:
        cached = None
        if resume_from_step in {"G4", "G5"}:
            cached = load_gate_artifact(outline_id=outline_id, section_key=section_key, gate="G3")

        if cached:
            validated = cached
        else:
            generated = context.get("stages", {}).get("generate", {})
            validated = _validate_stage(
                requirement_text=str(context.get("requirement_text", "")),
                generated=generated,
            )
            persist_gate_artifact(
                outline_id=outline_id,
                section_key=section_key,
                gate="G3",
                payload=validated,
            )
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G3",
            step_status="validating",
            resume_from_step="G4",
            last_error=None,
        )
        context.setdefault("stages", {})["validate"] = validated
        return context
    except Exception as exc:  # noqa: BLE001
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G3",
            step_status="failed",
            resume_from_step="G3",
            last_error=str(exc),
            retry_increment=1,
        )
        raise


@celery_app.task(bind=True, name="tasks.section_render_stage", max_retries=settings.task_max_retries)
def section_render_stage_task(self, context: dict) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "RENDER_EXPORT"})
    outline_id = str(context.get("outline_id", "") or "")
    section_key = str(context.get("section_key", "") or "")
    resume_from_step = str(context.get("resume_from_step", "G1") or "G1")
    try:
        cached = None
        if resume_from_step in {"G5"}:
            cached = load_gate_artifact(outline_id=outline_id, section_key=section_key, gate="G4")
        if cached:
            render_result = cached
            generated = context.get("stages", {}).get("generate", {})
        else:
            generated = context.get("stages", {}).get("generate", {})
            render_result = _render_stage(context=context, generated=generated)
            persist_gate_artifact(
                outline_id=outline_id,
                section_key=section_key,
                gate="G4",
                payload=render_result,
            )
        context.setdefault("stages", {})["render"] = render_result
        final_status = str(generated.get("status", "NEED_HUMAN_INPUT"))
        if final_status == "SUPPORTED" and render_result.get("status") == "FAILED":
            final_status = "FAILED"
        if final_status == "SUPPORTED" and render_result.get("status") == "SUCCEEDED":
            _safe_update_run_progress(
                outline_id=outline_id,
                current_step="G5",
                step_status="paused",
                resume_from_step="G5",
                last_error=None,
            )
        elif final_status == "FAILED":
            _safe_update_run_progress(
                outline_id=outline_id,
                current_step="G4",
                step_status="failed",
                resume_from_step="G4",
                last_error=str(render_result.get("error") or "render_failed"),
                retry_increment=1,
            )
        return {
            "status": final_status,
            "section_key": str(context.get("section_key", "")),
            "stages": context.get("stages", {}),
        }
    except Exception as exc:  # noqa: BLE001
        _safe_update_run_progress(
            outline_id=outline_id,
            current_step="G4",
            step_status="failed",
            resume_from_step="G4",
            last_error=str(exc),
            retry_increment=1,
        )
        raise


@celery_app.task(bind=True, name="tasks.section_pipeline", max_retries=settings.task_max_retries)
def section_pipeline_task(
    self,
    project_id: str,
    section_key: str,
    requirement_text: str,
    industry_tag: str | None = None,
) -> dict:  # type: ignore[no-untyped-def]
    """Fallback single-task pipeline: extract -> generate -> validate -> render."""
    outline_id = f"pipeline-{project_id}-{section_key}"
    context = section_extract_stage_task.run(outline_id, project_id, section_key, requirement_text, industry_tag, "G1")
    context = section_generate_stage_task.run(context)
    context = section_validate_stage_task.run(context)
    return section_render_stage_task.run(context)


def get_task_result(task_id: str) -> dict:
    task = AsyncResult(task_id, app=celery_app)
    payload = task.result if isinstance(task.result, dict) else None
    if payload is None and isinstance(task.info, dict):
        payload = task.info
    return {"task_id": task_id, "status": task.status, "result": payload}
