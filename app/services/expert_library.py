from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tables import DocKind, Document, EvidenceChunk, ExpertDoc, Project, SensitivityLevel
from app.schemas.contracts import (
    ExpertLibraryChunkItem,
    ExpertLibraryDocItem,
    ExpertLibraryIngestResponse,
    ExpertLibraryStructuredIngestItem,
    ExpertLibraryStructuredIngestResponse,
    EvidenceUpsertItem,
)
from app.services.historical_extractor import extract_evidence_chunks_from_text
from app.services.pdf_ingest import build_doc_blocks, extract_pages
from app.services.pricing_guard import detect_pricing_content
from app.services.qdrant_store import QdrantStore

_STRUCTURED_CATEGORY_MAP = {
    "STANDARD": ("规范", "STANDARD_SPEC", "STANDARD"),
    "COMPANY_PERFORMANCE": ("公司业绩", "COMPANY_PERFORMANCE", "PERFORMANCE"),
    "COMPANY_QUALIFICATION": ("公司资质", "COMPANY_QUALIFICATION", "QUALIFICATION"),
    "PM_QUALIFICATION_PERFORMANCE": ("项目管理人员资质及业绩", "PM_QUAL_PERFORMANCE", "PM_TEAM"),
}


@dataclass
class _ParsedProject:
    project_uuid: uuid.UUID | None
    project_raw: str | None


def _parse_project_id(project_id: str | None) -> _ParsedProject:
    if not project_id:
        return _ParsedProject(project_uuid=None, project_raw=None)
    try:
        return _ParsedProject(project_uuid=uuid.UUID(project_id), project_raw=project_id)
    except ValueError:
        return _ParsedProject(project_uuid=None, project_raw=project_id)


def _ensure_project_exists(project_uuid: uuid.UUID | None) -> None:
    if not project_uuid:
        return
    with SessionLocal() as db:
        exists = db.execute(select(Project.id).where(Project.id == project_uuid)).scalar_one_or_none()
        if exists:
            return
        db.add(
            Project(
                id=project_uuid,
                name=f"Imported-{str(project_uuid)[:8]}",
                owner_user_id="system",
                description="Auto-created for expert library import",
            )
        )
        db.commit()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_")
    return cleaned or "upload.pdf"


def _save_uploaded_pdf(filename: str, content: bytes) -> Path:
    base_dir = Path(settings.upload_dir) / "expert_library"
    base_dir.mkdir(parents=True, exist_ok=True)
    target = base_dir / f"{uuid.uuid4()}_{_safe_filename(filename)}"
    target.write_bytes(content)
    return target


def _fallback_chunks_from_blocks(
    *,
    blocks: list,
    industry_tag: str | None,
    doc_type: str,
    pricing_related: bool,
) -> list[EvidenceUpsertItem]:
    chunks: list[EvidenceUpsertItem] = []
    for idx, block in enumerate(blocks, start=1):
        text = (block.content_text or "").strip()
        if len(text) < 24:
            continue
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        chunks.append(
            EvidenceUpsertItem(
                chunk_id=f"fb-{idx}-{digest}",
                text=text,
                doc_type=doc_type,
                section_type="PARA",
                industry_tag=industry_tag,
                sensitivity_level="PUBLIC_OK",
                forbidden_tags=["PRICING_RELATED"] if pricing_related else [],
                source_locator={"page_no": block.page_no, "section_anchor": block.section_anchor},
            )
        )
    return chunks


def ingest_historical_pdf(
    *,
    filename: str,
    content: bytes,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str = "system",
    doc_type: str = "EXPERT_HISTORY",
    model_id: str | None = None,
) -> ExpertLibraryIngestResponse:
    parsed_project = _parse_project_id(project_id)
    _ensure_project_exists(parsed_project.project_uuid)

    saved_path = _save_uploaded_pdf(filename, content)
    pages = extract_pages(content, enable_ocr_fallback=settings.enable_ocr_fallback)
    blocks = build_doc_blocks(pages)
    full_text = "\n".join((block.content_text or "") for block in blocks if block.content_text)

    pricing_blocked, pricing_reasons = detect_pricing_content(full_text)
    warnings: list[str] = []
    if pricing_blocked:
        warnings.extend([f"pricing_detected:{reason}" for reason in pricing_reasons])

    chunks: list[EvidenceUpsertItem]
    if not pricing_blocked:
        try:
            chunks = extract_evidence_chunks_from_text(
                text=full_text,
                industry_tag=industry_tag,
                doc_type=doc_type,
                model_id=model_id,
                project_id=parsed_project.project_raw,
            )
        except Exception:  # noqa: BLE001
            chunks = _fallback_chunks_from_blocks(
                blocks=blocks,
                industry_tag=industry_tag,
                doc_type=doc_type,
                pricing_related=False,
            )
            warnings.append("langextract_failed_fallback_to_paragraph_chunks")
    else:
        chunks = _fallback_chunks_from_blocks(
            blocks=blocks,
            industry_tag=industry_tag,
            doc_type=doc_type,
            pricing_related=True,
        )
        warnings.append("langextract_skipped_due_to_pricing_content")

    if not chunks:
        chunks = _fallback_chunks_from_blocks(
            blocks=blocks,
            industry_tag=industry_tag,
            doc_type=doc_type,
            pricing_related=pricing_blocked,
        )
        warnings.append("no_structured_chunks_fallback_to_paragraph_chunks")

    source_document_id: uuid.UUID | None = None
    expert_doc_id: uuid.UUID
    try:
        with SessionLocal() as db:
            source_doc = Document(
                project_id=parsed_project.project_uuid,
                kind=DocKind.EXPERT,
                filename=filename,
                content_type="application/pdf",
                object_uri=str(saved_path),
                sha256=hashlib.sha256(content).hexdigest(),
                page_count=len(pages),
                language="zh-CN",
                sensitivity=SensitivityLevel.PUBLIC_OK,
                created_by=created_by,
            )
            db.add(source_doc)
            db.flush()
            source_document_id = source_doc.id

            expert_doc = ExpertDoc(
                source_document_id=source_document_id,
                doc_type=doc_type,
                title=title or filename,
                industry_tag=industry_tag,
                section_type="BID_HISTORY",
                sensitivity=SensitivityLevel.PUBLIC_OK,
                valid_from=date.today(),
                created_by=created_by,
            )
            db.add(expert_doc)
            db.flush()
            expert_doc_id = expert_doc.id

            for idx, chunk in enumerate(chunks, start=1):
                source_locator = chunk.source_locator or {}
                db.add(
                    EvidenceChunk(
                        expert_doc_id=expert_doc_id,
                        chunk_no=idx,
                        excerpt_text=chunk.text,
                        excerpt_hash=hashlib.sha1(chunk.text.encode("utf-8")).hexdigest(),
                        location={"section_anchor": source_locator.get("section_anchor"), "page_no": source_locator.get("page_no")},
                        source_locator=source_locator,
                        valid_to=date.fromisoformat(chunk.valid_to) if chunk.valid_to else None,
                        sensitivity_level=SensitivityLevel.PUBLIC_OK,
                        quality_score=float(chunk.quality_score),
                        forbidden_tags=chunk.forbidden_tags or [],
                        qdrant_point_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc_id}:{chunk.chunk_id}")),
                    )
                )

            db.commit()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist expert library records: {exc}") from exc

    store = QdrantStore()
    upserted = store.upsert_chunks(str(expert_doc_id), chunks, project_id=parsed_project.project_raw)

    return ExpertLibraryIngestResponse(
        status="SUCCEEDED",
        expert_doc_id=str(expert_doc_id),
        source_document_id=str(source_document_id) if source_document_id else None,
        filename=filename,
        page_count=len(pages),
        chunk_count=len(chunks),
        qdrant_upserted=upserted,
        warnings=warnings,
    )


def list_expert_docs(project_id: str | None, industry_tag: str | None, limit: int = 50) -> list[ExpertLibraryDocItem]:
    parsed_project = _parse_project_id(project_id)
    with SessionLocal() as db:
        stmt = (
            select(
                ExpertDoc.id,
                ExpertDoc.title,
                ExpertDoc.industry_tag,
                ExpertDoc.doc_type,
                ExpertDoc.created_at,
                func.count(EvidenceChunk.id),
            )
            .outerjoin(EvidenceChunk, EvidenceChunk.expert_doc_id == ExpertDoc.id)
            .group_by(ExpertDoc.id)
            .order_by(ExpertDoc.created_at.desc())
            .limit(max(1, min(limit, 200)))
        )
        if industry_tag:
            stmt = stmt.where(ExpertDoc.industry_tag == industry_tag)
        if parsed_project.project_uuid:
            stmt = stmt.join(Document, Document.id == ExpertDoc.source_document_id).where(
                Document.project_id == parsed_project.project_uuid
            )

        rows = db.execute(stmt).all()
        return [
            ExpertLibraryDocItem(
                expert_doc_id=str(row[0]),
                title=row[1],
                industry_tag=row[2],
                doc_type=row[3],
                created_at=row[4].isoformat() if isinstance(row[4], datetime) else str(row[4]),
                chunk_count=int(row[5] or 0),
            )
            for row in rows
        ]


def list_expert_chunks(expert_doc_id: str, limit: int = 200) -> list[ExpertLibraryChunkItem]:
    try:
        doc_uuid = uuid.UUID(expert_doc_id)
    except ValueError as exc:
        raise ValueError("invalid expert_doc_id") from exc

    with SessionLocal() as db:
        stmt = (
            select(EvidenceChunk)
            .where(EvidenceChunk.expert_doc_id == doc_uuid)
            .order_by(EvidenceChunk.chunk_no.asc())
            .limit(max(1, min(limit, 1000)))
        )
        rows = db.execute(stmt).scalars().all()
        items: list[ExpertLibraryChunkItem] = []
        for row in rows:
            source_locator = row.source_locator or {}
            items.append(
                ExpertLibraryChunkItem(
                    chunk_id=row.excerpt_hash or str(row.chunk_no),
                    excerpt_text=row.excerpt_text,
                    section_anchor=source_locator.get("section_anchor"),
                    quality_score=float(row.quality_score or 0),
                    valid_to=row.valid_to.isoformat() if row.valid_to else None,
                    created_at=row.created_at.isoformat() if row.created_at else "",
                )
            )
        return items


def _clean_lines(items: list[str]) -> list[str]:
    return [line.strip() for line in items if line and line.strip()]


def _build_structured_chunks(
    *,
    category_key: str,
    lines: list[str],
    industry_tag: str | None,
) -> list[EvidenceUpsertItem]:
    chunks: list[EvidenceUpsertItem] = []
    _, doc_type, section_type = _STRUCTURED_CATEGORY_MAP[category_key]
    for idx, text in enumerate(lines, start=1):
        digest = hashlib.sha1(f"{category_key}:{text}".encode("utf-8")).hexdigest()[:12]
        blocked, _ = detect_pricing_content(text)
        chunks.append(
            EvidenceUpsertItem(
                chunk_id=f"{category_key.lower()}-{idx}-{digest}",
                text=text,
                doc_type=doc_type,
                section_type=section_type,
                industry_tag=industry_tag,
                sensitivity_level="PUBLIC_OK",
                forbidden_tags=["PRICING_RELATED"] if blocked else [],
                quality_score=88.0,
                source_locator={"source": "structured_form", "category": category_key, "line": idx},
            )
        )
    return chunks


def _persist_structured_category(
    *,
    project_uuid: uuid.UUID | None,
    project_id: str | None,
    industry_tag: str | None,
    created_by: str,
    category_key: str,
    chunks: list[EvidenceUpsertItem],
) -> ExpertLibraryStructuredIngestItem:
    title, doc_type, section_type = _STRUCTURED_CATEGORY_MAP[category_key]
    text_blob = "\n".join(chunk.text for chunk in chunks)
    warnings: list[str] = []
    pricing_blocked, reasons = detect_pricing_content(text_blob)
    if pricing_blocked:
        warnings.extend([f"pricing_detected:{reason}" for reason in reasons])

    try:
        with SessionLocal() as db:
            source_doc = Document(
                project_id=project_uuid,
                kind=DocKind.EXPERT,
                filename=f"{title}.txt",
                content_type="text/plain",
                object_uri=f"local://expert_library/structured/{uuid.uuid4()}",
                sha256=hashlib.sha256(text_blob.encode("utf-8")).hexdigest(),
                page_count=1,
                language="zh-CN",
                sensitivity=SensitivityLevel.PUBLIC_OK,
                created_by=created_by,
            )
            db.add(source_doc)
            db.flush()

            expert_doc = ExpertDoc(
                source_document_id=source_doc.id,
                doc_type=doc_type,
                title=title,
                industry_tag=industry_tag,
                section_type=section_type,
                sensitivity=SensitivityLevel.PUBLIC_OK,
                valid_from=date.today(),
                created_by=created_by,
            )
            db.add(expert_doc)
            db.flush()

            for idx, chunk in enumerate(chunks, start=1):
                source_locator = chunk.source_locator or {}
                db.add(
                    EvidenceChunk(
                        expert_doc_id=expert_doc.id,
                        chunk_no=idx,
                        excerpt_text=chunk.text,
                        excerpt_hash=hashlib.sha1(chunk.text.encode("utf-8")).hexdigest(),
                        location={"section_anchor": section_type, "page_no": 1},
                        source_locator=source_locator,
                        valid_to=date.fromisoformat(chunk.valid_to) if chunk.valid_to else None,
                        sensitivity_level=SensitivityLevel.PUBLIC_OK,
                        quality_score=float(chunk.quality_score),
                        forbidden_tags=chunk.forbidden_tags or [],
                        qdrant_point_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc.id}:{chunk.chunk_id}")),
                    )
                )

            db.commit()
            expert_doc_id = str(expert_doc.id)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist structured expert library records: {exc}") from exc

    store = QdrantStore()
    upserted = store.upsert_chunks(expert_doc_id, chunks, project_id=project_id)
    return ExpertLibraryStructuredIngestItem(
        category=category_key,
        expert_doc_id=expert_doc_id,
        title=title,
        chunk_count=len(chunks),
        qdrant_upserted=upserted,
        warnings=warnings,
    )


def ingest_structured_expert_knowledge(
    *,
    project_id: str | None,
    industry_tag: str | None,
    created_by: str,
    standard_items: list[str],
    company_performance_items: list[str],
    company_qualification_items: list[str],
    pm_qualification_performance_items: list[str],
) -> ExpertLibraryStructuredIngestResponse:
    parsed_project = _parse_project_id(project_id)
    _ensure_project_exists(parsed_project.project_uuid)

    grouped = {
        "STANDARD": _clean_lines(standard_items),
        "COMPANY_PERFORMANCE": _clean_lines(company_performance_items),
        "COMPANY_QUALIFICATION": _clean_lines(company_qualification_items),
        "PM_QUALIFICATION_PERFORMANCE": _clean_lines(pm_qualification_performance_items),
    }
    if not any(grouped.values()):
        raise ValueError("at least one structured item is required")

    items: list[ExpertLibraryStructuredIngestItem] = []
    total_chunks = 0
    for category_key, lines in grouped.items():
        if not lines:
            continue
        chunks = _build_structured_chunks(
            category_key=category_key,
            lines=lines,
            industry_tag=industry_tag,
        )
        item = _persist_structured_category(
            project_uuid=parsed_project.project_uuid,
            project_id=parsed_project.project_raw,
            industry_tag=industry_tag,
            created_by=created_by,
            category_key=category_key,
            chunks=chunks,
        )
        items.append(item)
        total_chunks += item.chunk_count

    return ExpertLibraryStructuredIngestResponse(
        status="SUCCEEDED",
        total_docs=len(items),
        total_chunks=total_chunks,
        items=items,
    )
