from __future__ import annotations

from pathlib import Path

from celery.result import AsyncResult

from app.core.config import settings
from app.schemas.contracts import EvidenceUpsertItem
from app.services.evidence_validator import run_three_gates
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.historical_extractor import extract_evidence_chunks_from_text
from app.services.pdf_ingest import ingest_pdf_bytes
from app.services.qdrant_store import QdrantStore
from app.services.tender_parser import parse_tender_requirements
from app.workers.celery_app import celery_app


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
    parsed = parse_tender_requirements(tender_text)
    return {"status": parsed.status, "requirements": [r.model_dump() for r in parsed.requirements]}


@celery_app.task(bind=True, name="tasks.section_generate", max_retries=settings.task_max_retries)
def section_generate_task(
    self,
    project_id: str,
    section_key: str,
    requirement_text: str,
    industry_tag: str | None = None,
) -> dict:  # type: ignore[no-untyped-def]
    self.update_state(state="PROGRESS", meta={"stage": "SECTION_GENERATE"})
    result = generate_draft_with_retrieval(
        requirement_id=section_key,
        requirement_text=requirement_text,
        top_k=settings.top_k_default,
        project_id=project_id,
        industry_tag=industry_tag,
        retry_count=int(getattr(self.request, "retries", 0)),
        fallback_count=0,
    )
    return result.model_dump()


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
    store = QdrantStore()
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
    store = QdrantStore()
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


def get_task_result(task_id: str) -> dict:
    task = AsyncResult(task_id, app=celery_app)
    payload = task.result if isinstance(task.result, dict) else None
    if payload is None and isinstance(task.info, dict):
        payload = task.info
    return {"task_id": task_id, "status": task.status, "result": payload}
