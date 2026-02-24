from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import session_scope
from app.models.tables import DocKind, Document, EvidenceChunk, ExpertDoc, Project, SensitivityLevel
from app.schemas.contracts import (
    DocBlockItem,
    ExpertLibraryConvertResponse,
    ExpertLibraryChunkItem,
    ExpertLibraryDocItem,
    ExpertLibraryIngestResponse,
    ExpertLibraryStructuredIngestItem,
    ExpertLibraryStructuredIngestResponse,
    EvidenceUpsertItem,
)
from app.services.ingest.file_router import IngestedUploadPayload, ingest_upload_bytes
from app.services.path_safety import validate_path_identifier
from app.services.expert_enterprise_pipeline import (
    build_exceptions_queue,
    build_structure_v1_from_blocks,
    chunks_for_enterprise_rag,
    enrich_sections_v1,
    merge_structure_meta_risk,
    render_enterprise_markdown,
    risk_review_sections,
    serialize_chunks_jsonl,
    summarize_tables_in_structure,
)
from app.services.expert_workspace import (
    ExpertDocWorkspace,
    ensure_expert_library_layout,
    prepare_doc_workspace,
    sync_enterprise_config_assets,
)
from app.services.pricing_guard import detect_pricing_content
from app.services.qdrant_store import get_qdrant_store

_STRUCTURED_CATEGORY_MAP = {
    "STANDARD": ("规范", "STANDARD_SPEC", "STANDARD"),
    "COMPANY_PERFORMANCE": ("公司业绩", "COMPANY_PERFORMANCE", "PERFORMANCE"),
    "COMPANY_QUALIFICATION": ("公司资质", "COMPANY_QUALIFICATION", "QUALIFICATION"),
    "PM_QUALIFICATION_PERFORMANCE": ("项目管理人员资质及业绩", "PM_QUAL_PERFORMANCE", "PM_TEAM"),
    "SAFETY_PRODUCTION": ("安全生产", "SAFETY_PRODUCTION", "SAFETY"),
    "QUALITY_MANAGEMENT": ("质量管理", "QUALITY_MANAGEMENT", "QUALITY"),
    "ENVIRONMENTAL_PROTECTION": ("环境保护", "ENVIRONMENTAL_PROTECTION", "ENVIRONMENT"),
    "CONSTRUCTION_METHOD": ("施工工法", "CONSTRUCTION_METHOD", "CONSTRUCTION"),
    "EQUIPMENT_MATERIAL": ("设备材料", "EQUIPMENT_MATERIAL", "EQUIPMENT"),
    "FINANCIAL_CREDIT": ("财务信用", "FINANCIAL_CREDIT", "FINANCIAL"),
}

_CONVERSION_STAGE_DIR = "08_conversion_sessions"


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
    with session_scope() as db:
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
    return cleaned or "upload_file"


def _save_uploaded_file(filename: str, content: bytes, raw_bid_dir: Path) -> Path:
    target = raw_bid_dir / _safe_filename(filename)
    target.write_bytes(content)
    return target


def _save_json(path: Path, payload: dict | list) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_jsonl(path: Path, rows: list[dict]) -> None:
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(f"{content}\n" if content else "", encoding="utf-8")


def _append_jsonl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def _conversion_sessions_dir(layout) -> Path:
    target = layout.root / _CONVERSION_STAGE_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _validated_conversion_id(raw: str) -> str:
    return validate_path_identifier("conversion_id", raw)


def _conversion_session_dir(layout, conversion_id: str) -> Path:
    safe_conversion_id = _validated_conversion_id(conversion_id)
    directory = _conversion_sessions_dir(layout) / safe_conversion_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _load_conversion_meta(layout, conversion_id: str) -> tuple[Path, dict]:
    safe_conversion_id = _validated_conversion_id(conversion_id)
    session_dir = _conversion_sessions_dir(layout) / safe_conversion_id
    meta_path = session_dir / "meta.json"
    if not meta_path.exists():
        raise ValueError("conversion session not found")
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid conversion meta")
    return session_dir, payload


def _table_rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return "| 空表 |\n| --- |\n|  |"
    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:] if len(normalized) > 1 else [[""] * width]
    lines = [
        f"| {' | '.join(header)} |",
        f"| {' | '.join(['---'] * width)} |",
    ]
    lines.extend(f"| {' | '.join(row)} |" for row in body)
    return "\n".join(lines)


def _render_conversion_doc_markdown(
    *,
    title: str,
    structure: dict,
    page_meta: dict[int, dict[str, object]],
) -> str:
    lines = [f"# {title}", ""]
    for section in structure.get("sections", []):
        section_title = str(section.get("title") or "未命名章节")
        lines.append(f"## {section_title}")
        lines.append("")
        for block in section.get("blocks", []):
            block_id = str(block.get("block_id") or "block")
            page_no = int(block.get("page") or section.get("page_start") or 1)
            block_type = str(block.get("type") or "text").upper()
            source = str((page_meta.get(page_no) or {}).get("source") or "unknown")
            ocr_used = bool((page_meta.get(page_no) or {}).get("ocr_used", False))
            lines.append(f"<!-- page: {page_no} -->")
            lines.append(
                f"<!-- block: {block_id} type={block_type} source={source} ocr_used={'true' if ocr_used else 'false'} -->"
            )
            if block_type.lower() == "table":
                table = block.get("table") or {}
                rows = table.get("rows") or []
                lines.append(_table_rows_to_markdown(rows))
            else:
                lines.append(str(block.get("text") or ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _build_conversion_layout_rows(structure: dict, page_meta: dict[int, dict[str, object]]) -> list[dict]:
    rows: list[dict] = []
    for section in structure.get("sections", []):
        section_anchor = str(section.get("title") or "")
        for block in section.get("blocks", []):
            page_no = int(block.get("page") or section.get("page_start") or 1)
            info = page_meta.get(page_no) or {}
            rows.append(
                {
                    "block_id": str(block.get("block_id") or ""),
                    "page_no": page_no,
                    "block_type": "TABLE" if str(block.get("type", "")).lower() == "table" else "PARA",
                    "section_anchor": section_anchor,
                    "source": str(info.get("source") or "unknown"),
                    "ocr_used": bool(info.get("ocr_used", False)),
                }
            )
    return rows


def _build_conversion_chunk_rows(chunks: list[EvidenceUpsertItem]) -> list[dict]:
    rows: list[dict] = []
    for chunk in chunks:
        locator = chunk.source_locator or {}
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "doc_id": str(locator.get("doc_id") or ""),
                "section_path": str(locator.get("section_title") or locator.get("section_id") or ""),
                "page_range": str(locator.get("source_page") or ""),
                "text": chunk.text,
                "payload": locator,
            }
        )
    return rows


def _structure_doc_type(doc_type: str) -> str:
    normalized = (doc_type or "").strip().upper()
    if "SPEC" in normalized:
        return "spec"
    if "MANUAL" in normalized:
        return "manual"
    if normalized:
        return "bid"
    return "other"


def _write_extracted_blocks(structure: dict, blocks_dir: Path) -> None:
    for section in structure.get("sections", []):
        for block in section.get("blocks", []):
            block_id = str(block.get("block_id") or "block")
            block_type = str(block.get("type", "")).lower()
            if block_type == "table":
                payload = block.get("table") or {}
                (blocks_dir / f"{block_id}.json").write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            elif block_type == "text":
                (blocks_dir / f"{block_id}.txt").write_text(str(block.get("text", "")), encoding="utf-8")


def _write_review_yaml(path: Path, doc_id: str, exceptions: list[dict]) -> None:
    lines = [
        f"doc_id: {doc_id}",
        f"issue_count: {len(exceptions)}",
        "issues:",
    ]
    for item in exceptions:
        lines.append(f"  - issue: {item.get('issue')}")
        lines.append(f"    section_id: {item.get('section_id')}")
        lines.append(f"    action: {item.get('action')}")
        lines.append(f"    detail: {item.get('detail')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_pipeline_run_log(
    *,
    layout,
    doc_id: str,
    filename: str,
    chunk_count: int,
    exception_count: int,
    warnings: list[str],
    pricing_blocked: bool,
) -> None:
    run_dir = layout.stage_dirs["99_logs"] / "pipeline_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    payload = {
        "run_id": f"{stamp}_run01",
        "doc_id": doc_id,
        "filename": filename,
        "status": "SUCCEEDED",
        "chunk_count": chunk_count,
        "exception_count": exception_count,
        "pricing_blocked": pricing_blocked,
        "warnings": warnings,
        "stages": [
            "classify_files",
            "extract_structure",
            "summarize_tables",
            "enrich_sections",
            "risk_review",
            "merge_and_validate",
            "render_markdown",
            "chunk_for_rag",
        ],
    }
    _save_json(run_dir / f"{stamp}_run01.json", payload)


def _load_thresholds(layout) -> dict[str, float]:
    defaults: dict[str, float] = {
        "low_confidence": 0.60,
        "strong_review_confidence": 0.75,
        "max_section_pages": 20.0,
        "max_chunk_tokens": float(settings.expert_chunk_max_tokens),
        "chunk_overlap_tokens": float(settings.expert_chunk_overlap_tokens),
    }
    config_path = layout.root / "00_config" / "pipeline" / "thresholds.v1.yaml"
    if not config_path.exists():
        return defaults

    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key not in defaults:
            continue
        try:
            defaults[key] = float(value)
        except ValueError:
            continue
    return defaults


def _fallback_chunks_from_blocks(
    *,
    blocks: list,
    industry_tag: str | None,
    doc_type: str,
    pricing_related: bool,
    doc_id: str,
) -> list[EvidenceUpsertItem]:
    chunks: list[EvidenceUpsertItem] = []
    for idx, block in enumerate(blocks, start=1):
        text = (block.content_text or "").strip()
        if len(text) < settings.chunk_min_char_length:
            continue
        page_no = int(getattr(block, "page_no", 1) or 1)
        section_id = f"fb-sec-{idx:04d}"
        section_type = "TABLE" if str(getattr(block, "block_type", "")).upper() == "TABLE" else "PARA"
        digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        chunks.append(
            EvidenceUpsertItem(
                chunk_id=f"fb-{idx}-{digest}",
                text=text,
                doc_type=doc_type,
                section_type=section_type,
                industry_tag=industry_tag,
                sensitivity_level="PUBLIC_OK",
                forbidden_tags=["PRICING_RELATED"] if pricing_related else [],
                source_locator={
                    "doc_id": doc_id,
                    "section_id": section_id,
                    "section_type": section_type,
                    "discipline": industry_tag or "GENERAL",
                    "source_page": page_no,
                    "section_anchor": block.section_anchor,
                    "block_type": "table" if section_type == "TABLE" else "text",
                },
            )
        )
    return chunks


def _decode_text_content(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _looks_like_markdown_table(lines: list[str]) -> bool:
    if len(lines) < 2:
        return False
    if "|" not in lines[0] or "|" not in lines[1]:
        return False
    return bool(re.match(r"^\s*\|?[\s:\-|]+\|?\s*$", lines[1]))


def _build_text_blocks(*, text: str, default_anchor: str, markdown_mode: bool = False) -> list[DocBlockItem]:
    blocks: list[DocBlockItem] = []
    current_anchor = (default_anchor or "未命名章节").strip()[:48] or "未命名章节"
    cursor = 0

    for paragraph in [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            continue
        first_line = lines[0]
        heading_match = re.match(r"^\s{0,3}#{1,6}\s*(.+)$", first_line)
        if heading_match:
            current_anchor = heading_match.group(1).strip()[:48] or current_anchor
        elif re.match(r"^\s*(第[一二三四五六七八九十0-9]+[章节条款]|\d+(?:\.\d+)+)", first_line):
            current_anchor = first_line[:48]

        block_type = "TABLE" if markdown_mode and _looks_like_markdown_table(lines) else "PARA"
        start = cursor
        end = cursor + len(paragraph)
        cursor = end + 1
        blocks.append(
            DocBlockItem(
                page_no=1,
                block_type=block_type,
                section_anchor=current_anchor,
                content_text=paragraph,
                char_start=start,
                char_end=end,
            )
        )
    return blocks


def _extract_upload_blocks(
    filename: str,
    content: bytes,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> tuple[list[DocBlockItem], int, str, str, str]:
    ext = Path(filename).suffix.lower()
    if ext in {".pdf", ".docx"}:
        payload = ingest_upload_bytes(
            filename=filename,
            file_bytes=content,
            enable_ocr_fallback=settings.enable_ocr_fallback,
            ocr_provider=ocr_provider,
            ocr_api_key=ocr_api_key,
            ocr_base_url=ocr_base_url,
            ocr_model=ocr_model,
        )
        if not payload.blocks:
            raise ValueError("empty document content")
        return (
            payload.blocks,
            payload.page_count,
            payload.source_format,
            payload.content_type,
            payload.parser_version,
        )
    if ext in {".md", ".markdown"}:
        text = _decode_text_content(content)
        blocks = _build_text_blocks(text=text, default_anchor=Path(filename).stem, markdown_mode=True)
        if not blocks:
            raise ValueError("empty markdown content")
        return (
            blocks,
            1,
            "markdown",
            "text/markdown",
            "markdown_ingest.v1",
        )
    if ext == ".doc":
        raise ValueError("暂不支持 .doc，请另存为 .docx 后上传")
    raise ValueError("unsupported file format, allowed: .pdf/.docx/.md/.markdown")


def _ingest_historical_with_blocks(
    *,
    filename: str,
    content: bytes,
    blocks: list[DocBlockItem],
    page_count: int,
    source_format: str,
    content_type: str,
    parser_version: str,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str = "system",
    doc_type: str = "EXPERT_HISTORY",
    model_id: str | None = None,
) -> ExpertLibraryIngestResponse:
    parsed_project = _parse_project_id(project_id)
    _ensure_project_exists(parsed_project.project_uuid)

    layout = ensure_expert_library_layout()
    sync_enterprise_config_assets(layout)
    thresholds = _load_thresholds(layout)

    full_text = "\n".join((block.content_text or "") for block in blocks if block.content_text)

    pricing_blocked, pricing_reasons = detect_pricing_content(full_text)
    warnings: list[str] = []
    if (model_id or "").strip():
        warnings.append("model_id_ignored_in_section_chunking_pipeline")
    if pricing_blocked:
        warnings.extend([f"pricing_detected:{reason}" for reason in pricing_reasons])
        warnings.append("section_enhancement_chunking_with_pricing_redaction_flags")

    doc_workspace: ExpertDocWorkspace | None = None
    structure: dict[str, Any] | None = None
    table_summaries: list[dict] = []
    section_meta: list[dict] = []
    risk_reviews: list[dict] = []
    merged: dict[str, Any] | None = None
    exception_queue: list[dict] = []
    markdown: str | None = None

    source_document_id: uuid.UUID | None = None
    expert_doc_id: uuid.UUID
    chunks: list[EvidenceUpsertItem] = []

    try:
        with session_scope() as db:
            doc_workspace = prepare_doc_workspace(layout, title or Path(filename).stem)
            saved_path = _save_uploaded_file(filename, content, doc_workspace.raw_bid_dir)

            source_doc = Document(
                project_id=parsed_project.project_uuid,
                kind=DocKind.EXPERT,
                filename=filename,
                content_type=content_type,
                object_uri=str(saved_path),
                sha256=hashlib.sha256(content).hexdigest(),
                page_count=page_count,
                language="zh-CN",
                sensitivity=SensitivityLevel.PUBLIC_OK,
                created_by=created_by,
            )
            db.add(source_doc)
            db.flush()
            source_document_id = source_doc.id
            doc_id = f"{doc_workspace.doc_key}-{str(source_document_id)[:8]}"

            structure = build_structure_v1_from_blocks(
                doc_id=doc_id,
                title=title,
                source_file=filename,
                source_format=source_format,
                blocks=blocks,
                parser_version=parser_version,
                doc_type=_structure_doc_type(doc_type),
            )
            table_summaries = summarize_tables_in_structure(structure)
            section_meta = enrich_sections_v1(structure, table_summaries)
            risk_reviews = risk_review_sections(
                structure,
                section_meta,
                strong_review_confidence=float(thresholds["strong_review_confidence"]),
            )
            merged = merge_structure_meta_risk(structure, section_meta, risk_reviews)
            exception_queue = build_exceptions_queue(
                doc_id=doc_id,
                merged=merged,
                low_confidence=float(thresholds["low_confidence"]),
                max_section_pages=int(thresholds["max_section_pages"]),
            )
            markdown = render_enterprise_markdown(merged)
            chunks = chunks_for_enterprise_rag(
                merged,
                industry_tag=industry_tag,
                doc_type=doc_type,
                min_tokens=settings.expert_chunk_min_tokens,
                max_tokens=int(thresholds["max_chunk_tokens"]),
                overlap_tokens=int(thresholds["chunk_overlap_tokens"]),
            )

            if not chunks:
                chunks = _fallback_chunks_from_blocks(
                    blocks=blocks,
                    industry_tag=industry_tag,
                    doc_type=doc_type,
                    pricing_related=pricing_blocked,
                    doc_id=doc_id,
                )
                warnings.append("no_section_chunks_fallback_to_block_chunks")

            if pricing_blocked:
                for chunk in chunks:
                    tags = list(chunk.forbidden_tags or [])
                    if "PRICING_RELATED" not in tags:
                        tags.append("PRICING_RELATED")
                    chunk.forbidden_tags = tags

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
                source_page = source_locator.get("source_page")
                db.add(
                    EvidenceChunk(
                        expert_doc_id=expert_doc_id,
                        chunk_no=idx,
                        excerpt_text=chunk.text,
                        excerpt_hash=hashlib.sha1(chunk.text.encode("utf-8")).hexdigest(),
                        location={
                            "section_anchor": source_locator.get("section_title")
                            or source_locator.get("section_anchor"),
                            "page_no": source_page,
                        },
                        source_locator=source_locator,
                        valid_to=date.fromisoformat(chunk.valid_to) if chunk.valid_to else None,
                        sensitivity_level=SensitivityLevel.PUBLIC_OK,
                        quality_score=float(chunk.quality_score),
                        forbidden_tags=chunk.forbidden_tags or [],
                        qdrant_point_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc_id}:{chunk.chunk_id}")),
                        parent_chunk_id=chunk.parent_chunk_id or source_locator.get("parent_chunk_id"),
                        anchor_type=chunk.anchor_type or source_locator.get("anchor_type"),
                    )
                )

            db.commit()
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist expert library records: {exc}") from exc

    store = get_qdrant_store()
    upserted = store.upsert_chunks(str(expert_doc_id), chunks, project_id=parsed_project.project_raw)

    if source_document_id and doc_workspace and structure and merged and markdown is not None:
        _save_json(doc_workspace.extracted_dir / "structure.v1.json", structure)
        _write_extracted_blocks(structure, doc_workspace.extracted_blocks_dir)
        _save_jsonl(doc_workspace.enriched_dir / "table_summary.v1.jsonl", table_summaries)
        _save_jsonl(doc_workspace.enriched_dir / "section_meta.v1.jsonl", section_meta)
        _save_jsonl(doc_workspace.enriched_dir / "risk_review.v1.jsonl", risk_reviews)
        _save_json(doc_workspace.enriched_dir / "merged.v1.json", merged)

        (layout.stage_dirs["04_md"] / f"{doc_workspace.doc_key}.enhanced.md").write_text(markdown, encoding="utf-8")
        _save_jsonl(doc_workspace.chunks_dir / "chunks.v1.jsonl", serialize_chunks_jsonl(chunks))

        _save_json(
            layout.stage_dirs["06_index"] / "qdrant" / f"{doc_workspace.doc_key}.json",
            {
                "expert_doc_id": str(expert_doc_id),
                "source_document_id": str(source_document_id),
                "qdrant_upserted": upserted,
                "chunk_count": len(chunks),
            },
        )
        _append_jsonl(layout.stage_dirs["07_review"] / "exceptions.queue.jsonl", exception_queue)
        _write_review_yaml(
            layout.stage_dirs["07_review"] / f"{doc_workspace.doc_key}.review.yaml",
            doc_id=str(merged.get("doc_id", "")),
            exceptions=exception_queue,
        )
        _write_pipeline_run_log(
            layout=layout,
            doc_id=str(merged.get("doc_id", "")),
            filename=filename,
            chunk_count=len(chunks),
            exception_count=len(exception_queue),
            warnings=warnings,
            pricing_blocked=pricing_blocked,
        )

    return ExpertLibraryIngestResponse(
        status="SUCCEEDED",
        expert_doc_id=str(expert_doc_id),
        source_document_id=str(source_document_id) if source_document_id else None,
        filename=filename,
        page_count=page_count,
        chunk_count=len(chunks),
        qdrant_upserted=upserted,
        warnings=warnings,
    )


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
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> ExpertLibraryIngestResponse:
    blocks, page_count, source_format, content_type, parser_version = _extract_upload_blocks(
        filename,
        content,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
    )
    return _ingest_historical_with_blocks(
        filename=filename,
        content=content,
        blocks=blocks,
        page_count=page_count,
        source_format=source_format,
        content_type=content_type,
        parser_version=parser_version,
        project_id=project_id,
        industry_tag=industry_tag,
        title=title,
        created_by=created_by,
        doc_type=doc_type,
        model_id=model_id,
    )


def convert_upload_to_structured(
    *,
    filename: str,
    content: bytes,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str = "system",
    doc_type: str = "EXPERT_HISTORY",
    model_id: str | None = None,
    ocr_provider: str | None = None,
    ocr_api_key: str | None = None,
    ocr_base_url: str | None = None,
    ocr_model: str | None = None,
) -> ExpertLibraryConvertResponse:
    layout = ensure_expert_library_layout()
    sync_enterprise_config_assets(layout)
    thresholds = _load_thresholds(layout)

    payload: IngestedUploadPayload = ingest_upload_bytes(
        filename=filename,
        file_bytes=content,
        enable_ocr_fallback=settings.enable_ocr_fallback,
        ocr_provider=ocr_provider,
        ocr_api_key=ocr_api_key,
        ocr_base_url=ocr_base_url,
        ocr_model=ocr_model,
    )
    if not payload.blocks:
        raise ValueError("empty document content")

    full_text = payload.full_text
    pricing_blocked, pricing_reasons = detect_pricing_content(full_text)
    warnings: list[str] = []
    if (model_id or "").strip():
        warnings.append("model_id_ignored_in_section_chunking_pipeline")
    if pricing_blocked:
        warnings.extend([f"pricing_detected:{reason}" for reason in pricing_reasons])
        warnings.append("section_enhancement_chunking_with_pricing_redaction_flags")

    conversion_id = uuid.uuid4().hex
    session_dir = _conversion_session_dir(layout, conversion_id)
    raw_name = _safe_filename(filename)
    raw_path = session_dir / raw_name
    raw_path.write_bytes(content)

    doc_id = f"conv-{conversion_id[:12]}"
    structure = build_structure_v1_from_blocks(
        doc_id=doc_id,
        title=title,
        source_file=filename,
        source_format=payload.source_format,
        blocks=payload.blocks,
        parser_version=payload.parser_version,
        doc_type=_structure_doc_type(doc_type),
    )
    table_summaries = summarize_tables_in_structure(structure)
    section_meta = enrich_sections_v1(structure, table_summaries)
    risk_reviews = risk_review_sections(
        structure,
        section_meta,
        strong_review_confidence=float(thresholds["strong_review_confidence"]),
    )
    merged = merge_structure_meta_risk(structure, section_meta, risk_reviews)
    exception_queue = build_exceptions_queue(
        doc_id=doc_id,
        merged=merged,
        low_confidence=float(thresholds["low_confidence"]),
        max_section_pages=int(thresholds["max_section_pages"]),
    )
    chunks = chunks_for_enterprise_rag(
        merged,
        industry_tag=industry_tag,
        doc_type=doc_type,
        min_tokens=settings.expert_chunk_min_tokens,
        max_tokens=int(thresholds["max_chunk_tokens"]),
        overlap_tokens=int(thresholds["chunk_overlap_tokens"]),
    )
    if not chunks:
        chunks = _fallback_chunks_from_blocks(
            blocks=payload.blocks,
            industry_tag=industry_tag,
            doc_type=doc_type,
            pricing_related=pricing_blocked,
            doc_id=doc_id,
        )
        warnings.append("no_section_chunks_fallback_to_block_chunks")
    if pricing_blocked:
        for chunk in chunks:
            tags = list(chunk.forbidden_tags or [])
            if "PRICING_RELATED" not in tags:
                tags.append("PRICING_RELATED")
            chunk.forbidden_tags = tags

    doc_md_text = _render_conversion_doc_markdown(
        title=title or Path(filename).stem,
        structure=structure,
        page_meta=payload.page_meta,
    )
    layout_rows = _build_conversion_layout_rows(structure, payload.page_meta)
    chunk_rows = _build_conversion_chunk_rows(chunks)

    doc_md_path = session_dir / "doc.md"
    layout_json_path = session_dir / "layout.json"
    chunks_jsonl_path = session_dir / "chunks.jsonl"
    blocks_path = session_dir / "blocks.json"
    structure_path = session_dir / "structure.v1.json"
    merged_path = session_dir / "merged.v1.json"
    meta_path = session_dir / "meta.json"

    doc_md_path.write_text(doc_md_text, encoding="utf-8")
    _save_json(layout_json_path, layout_rows)
    _save_jsonl(chunks_jsonl_path, chunk_rows)
    _save_json(blocks_path, [block.model_dump() for block in payload.blocks])
    _save_json(structure_path, structure)
    _save_json(merged_path, merged)
    _save_json(
        meta_path,
        {
            "conversion_id": conversion_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "filename": filename,
            "raw_file": raw_name,
            "page_count": payload.page_count,
            "source_format": payload.source_format,
            "content_type": payload.content_type,
            "parser_version": payload.parser_version,
            "project_id": project_id,
            "industry_tag": industry_tag,
            "title": title,
            "created_by": created_by,
            "doc_type": doc_type,
            "model_id": model_id,
            "warnings": warnings,
            "artifacts": {
                "doc_md": str(doc_md_path),
                "layout_json": str(layout_json_path),
                "chunks_jsonl": str(chunks_jsonl_path),
                "structure_json": str(structure_path),
                "merged_json": str(merged_path),
                "blocks_json": str(blocks_path),
            },
            "exception_count": len(exception_queue),
            "block_count": len(payload.blocks),
            "section_count": len(structure.get("sections", [])),
            "chunk_count": len(chunks),
            "pricing_blocked": pricing_blocked,
        },
    )

    preview_sections = [str(section.get("title") or "") for section in structure.get("sections", [])][:8]
    return ExpertLibraryConvertResponse(
        status="SUCCEEDED",
        conversion_id=conversion_id,
        filename=filename,
        page_count=payload.page_count,
        block_count=len(payload.blocks),
        section_count=len(structure.get("sections", [])),
        chunk_count=len(chunks),
        preview_sections=preview_sections,
        artifacts={
            "doc_md": str(doc_md_path),
            "layout_json": str(layout_json_path),
            "chunks_jsonl": str(chunks_jsonl_path),
        },
        warnings=warnings,
    )


def confirm_structured_conversion_ingest(
    *,
    conversion_id: str,
    project_id: str | None,
    industry_tag: str | None,
    title: str | None,
    created_by: str = "system",
    doc_type: str = "EXPERT_HISTORY",
    model_id: str | None = None,
) -> ExpertLibraryIngestResponse:
    layout = ensure_expert_library_layout()
    session_dir, meta = _load_conversion_meta(layout, conversion_id)

    filename = str(meta.get("filename") or "")
    raw_file = str(meta.get("raw_file") or "")
    raw_path = session_dir / raw_file
    if not filename or not raw_file or not raw_path.exists():
        raise ValueError("invalid conversion session payload")

    blocks_path = session_dir / "blocks.json"
    if not blocks_path.exists():
        raise ValueError("conversion blocks not found")
    rows = json.loads(blocks_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("invalid conversion blocks")
    blocks = [DocBlockItem(**item) for item in rows]
    if not blocks:
        raise ValueError("conversion blocks are empty")

    resolved_project_id = project_id if project_id is not None else str(meta.get("project_id") or "") or None
    resolved_industry_tag = industry_tag if industry_tag is not None else str(meta.get("industry_tag") or "") or None
    resolved_title = title if title is not None else str(meta.get("title") or "") or None
    resolved_doc_type = (doc_type or "").strip() or str(meta.get("doc_type") or "EXPERT_HISTORY")
    resolved_model_id = model_id if model_id is not None else str(meta.get("model_id") or "") or None

    result = _ingest_historical_with_blocks(
        filename=filename,
        content=raw_path.read_bytes(),
        blocks=blocks,
        page_count=int(meta.get("page_count") or 1),
        source_format=str(meta.get("source_format") or "pdf"),
        content_type=str(meta.get("content_type") or "application/pdf"),
        parser_version=str(meta.get("parser_version") or "conversion.v1"),
        project_id=resolved_project_id,
        industry_tag=resolved_industry_tag,
        title=resolved_title,
        created_by=created_by,
        doc_type=resolved_doc_type,
        model_id=resolved_model_id,
    )

    meta["confirmed_at"] = datetime.now().isoformat(timespec="seconds")
    meta["confirmed_expert_doc_id"] = result.expert_doc_id
    _save_json(session_dir / "meta.json", meta)
    return result


def list_expert_docs(project_id: str | None, industry_tag: str | None, limit: int = 50) -> list[ExpertLibraryDocItem]:
    parsed_project = _parse_project_id(project_id)
    with session_scope() as db:
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

    with session_scope() as db:
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
        with session_scope() as db:
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
                source_locator = dict(chunk.source_locator or {})
                source_locator.setdefault("doc_id", str(source_doc.id))
                source_locator.setdefault("section_id", f"{category_key.lower()}-{idx:03d}")
                source_locator.setdefault("section_type", section_type)
                source_locator.setdefault("discipline", industry_tag or "GENERAL")
                source_locator.setdefault("source_page", 1)
                source_locator.setdefault("block_type", "text")
                source_locator.setdefault("section_title", title)
                chunk.source_locator = source_locator
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
                        parent_chunk_id=chunk.parent_chunk_id or source_locator.get("parent_chunk_id"),
                        anchor_type=chunk.anchor_type or source_locator.get("anchor_type"),
                    )
                )

            db.commit()
            expert_doc_id = str(expert_doc.id)
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist structured expert library records: {exc}") from exc

    store = get_qdrant_store()
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
