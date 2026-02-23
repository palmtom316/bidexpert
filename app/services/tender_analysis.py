from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import session_scope
from app.models.tables import (
    DocKind,
    Document,
    Project,
    SensitivityLevel,
    TenderAnalysisRun,
    TenderKeyCategory,
    TenderKeyInfo,
)
from app.schemas.contracts import (
    ParsedRequirement,
    TenderAnalysisDetailResponse,
    TenderAnalysisRunItem,
    TenderAnalysisSummary,
    TenderKeyInfoItem,
)
from app.services.pdf_ingest import extract_pages
from app.services.pricing_guard import detect_pricing_content
from app.extract.tender_parser import ANCHOR_PATTERN, SCORE_PATTERN, parse_tender_requirements

_SENTENCE_SPLIT = re.compile(r"[。；;\n]+")
_MUST_PATTERN = re.compile(r"(必须|应当|不得|须|需|符合|满足|提交|提供)")
_SCORING_PATTERN = re.compile(r"(评分|分值|得分|评审|评分办法|评分标准|扣分)")
_BONUS_PATTERN = re.compile(r"(加分|优先|奖励|额外分|附加分|同等条件优先|优先考虑)")
_PENALTY_PATTERN = re.compile(r"(扣分|减分|每项扣|每处扣)")
_BIDDING_PATTERN = re.compile(r"(投标|方案|技术|服务|实施|交付|工期|团队|资质|业绩|案例|保障)")
_RISK_PATTERN = re.compile(r"(废标|无效标|不予受理|拒绝|保证金|罚则|违约|否决|资格审查不通过|取消投标资格)")


@dataclass
class _LineInsight:
    category: TenderKeyCategory
    content: str
    page_no: int
    section_anchor: str | None
    score_weight: float | None
    is_must: bool
    importance: int


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", name).strip("_") or "tender.pdf"


def _parse_project_uuid(project_id: str | None) -> uuid.UUID | None:
    if not project_id:
        return None
    try:
        return uuid.UUID(project_id)
    except ValueError:
        return None


def _ensure_project(project_uuid: uuid.UUID | None) -> None:
    if not project_uuid:
        return
    with session_scope() as db:
        exists = db.execute(select(Project.id).where(Project.id == project_uuid)).scalar_one_or_none()
        if exists:
            return
        db.add(
            Project(
                id=project_uuid,
                name=f"Tender-{str(project_uuid)[:8]}",
                owner_user_id="system",
                description="Auto created for tender analysis",
            )
        )
        db.commit()


def _save_file(filename: str, content: bytes) -> Path:
    target_dir = Path(settings.upload_dir) / "tender_analysis"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{uuid.uuid4()}_{_safe_filename(filename)}"
    target.write_bytes(content)
    return target


def _extract_lines(page_no: int, text: str) -> list[tuple[str, str | None]]:
    lines: list[tuple[str, str | None]] = []
    current_anchor: str | None = None
    for raw in _SENTENCE_SPLIT.split(text):
        line = raw.strip()
        if len(line) < 6:
            continue
        if ANCHOR_PATTERN.match(line):
            current_anchor = line[:48]
        lines.append((line, current_anchor))
    return lines


def _score_weight(text: str) -> float | None:
    m = SCORE_PATTERN.search(text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _classify_line(*, content: str, page_no: int, section_anchor: str | None) -> list[_LineInsight]:
    score = _score_weight(content)
    is_must = bool(_MUST_PATTERN.search(content))
    is_bonus = bool(_BONUS_PATTERN.search(content))
    is_penalty = bool(_PENALTY_PATTERN.search(content))
    is_scoring = bool(_SCORING_PATTERN.search(content)) or score is not None or is_bonus or is_penalty
    is_bidding = bool(_BIDDING_PATTERN.search(content)) or ("要求" in content and len(content) >= 10)
    is_risk = bool(_RISK_PATTERN.search(content))

    items: list[_LineInsight] = []
    if is_bidding:
        items.append(
            _LineInsight(
                category=TenderKeyCategory.BIDDING_POINTS,
                content=content,
                page_no=page_no,
                section_anchor=section_anchor,
                score_weight=score,
                is_must=is_must,
                importance=55 + (15 if is_must else 0),
            )
        )
    if is_scoring:
        items.append(
            _LineInsight(
                category=TenderKeyCategory.SCORING_POINTS,
                content=content,
                page_no=page_no,
                section_anchor=section_anchor,
                score_weight=score,
                is_must=is_must,
                importance=60 + min(int(score or 0), 30),
            )
        )
    if is_must:
        items.append(
            _LineInsight(
                category=TenderKeyCategory.COMPLIANCE_REQUIREMENTS,
                content=content,
                page_no=page_no,
                section_anchor=section_anchor,
                score_weight=score,
                is_must=True,
                importance=75,
            )
        )
    if is_bonus:
        items.append(
            _LineInsight(
                category=TenderKeyCategory.BONUS_POINTS,
                content=content,
                page_no=page_no,
                section_anchor=section_anchor,
                score_weight=score,
                is_must=False,
                importance=70,
            )
        )
    if is_risk:
        items.append(
            _LineInsight(
                category=TenderKeyCategory.RISK_ALERTS,
                content=content,
                page_no=page_no,
                section_anchor=section_anchor,
                score_weight=score,
                is_must=is_must,
                importance=80,
            )
        )
    return items


def _insights_from_parsed_requirements(items: list[ParsedRequirement]) -> list[_LineInsight]:
    mapped: list[_LineInsight] = []
    for req in items:
        content = req.original_text.strip()
        if not content:
            continue

        page_no = req.page_no if isinstance(req.page_no, int) and req.page_no > 0 else 1
        section_anchor = req.section_anchor.strip() if req.section_anchor else None
        score_weight = float(req.score_weight) if req.score_weight is not None else _score_weight(content)
        is_must = bool(req.is_must)
        format_required = bool((req.format_constraints or {}).get("format_required"))
        disqualify_rule = bool((req.format_constraints or {}).get("disqualify_rule"))
        scoring_rule_type = str((req.format_constraints or {}).get("scoring_rule_type") or "").lower()
        is_bonus = scoring_rule_type == "bonus" or bool(_BONUS_PATTERN.search(content))
        is_penalty = scoring_rule_type == "penalty" or bool(_PENALTY_PATTERN.search(content))
        is_scoring = score_weight is not None or bool(_SCORING_PATTERN.search(content)) or is_bonus or is_penalty
        is_bidding = bool(_BIDDING_PATTERN.search(content)) or ("要求" in content and len(content) >= 10) or format_required
        is_risk = disqualify_rule or bool(_RISK_PATTERN.search(content))

        if is_bidding:
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.BIDDING_POINTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=is_must,
                    importance=58 + (15 if is_must else 0),
                )
            )
        if is_scoring:
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.SCORING_POINTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=is_must,
                    importance=60 + min(int(score_weight or 0), 30),
                )
            )
        if is_must:
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.COMPLIANCE_REQUIREMENTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=True,
                    importance=75,
                )
            )
        if is_bonus:
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.BONUS_POINTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=False,
                    importance=70,
                )
            )
        if is_risk:
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.RISK_ALERTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=is_must,
                    importance=80,
                )
            )
        if not any((is_bidding, is_scoring, is_must, is_bonus, is_risk)):
            mapped.append(
                _LineInsight(
                    category=TenderKeyCategory.BIDDING_POINTS,
                    content=content,
                    page_no=page_no,
                    section_anchor=section_anchor,
                    score_weight=score_weight,
                    is_must=is_must,
                    importance=50,
                )
            )
    return _dedupe(mapped)


def _dedupe(items: list[_LineInsight]) -> list[_LineInsight]:
    best: dict[tuple[TenderKeyCategory, str], _LineInsight] = {}
    for item in items:
        key = (item.category, item.content)
        current = best.get(key)
        if not current or item.importance > current.importance:
            best[key] = item
    return list(best.values())


def _summary(items: list[_LineInsight], warnings: list[str]) -> TenderAnalysisSummary:
    counts: dict[str, int] = {}
    sections: list[str] = []
    seen_sections: set[str] = set()
    for item in items:
        counts[item.category.value] = counts.get(item.category.value, 0) + 1
        if item.section_anchor and item.section_anchor not in seen_sections:
            seen_sections.add(item.section_anchor)
            sections.append(item.section_anchor)
    return TenderAnalysisSummary(
        total_items=len(items),
        category_counts=counts,
        key_sections=sections[:12],
        warnings=warnings,
    )


def _item_title(item: _LineInsight) -> str:
    if item.section_anchor:
        return item.section_anchor
    return item.content[:18]


def analyze_and_persist_tender_pdf(
    *,
    filename: str,
    content: bytes,
    project_id: str | None,
    created_by: str = "system",
) -> tuple[TenderAnalysisRunItem, TenderAnalysisSummary]:
    project_uuid = _parse_project_uuid(project_id)
    _ensure_project(project_uuid)

    pages = extract_pages(content, enable_ocr_fallback=settings.enable_ocr_fallback)
    full_text = "\f".join(page.text for page in pages)
    pricing_hit, reasons = detect_pricing_content(full_text)
    warnings = [f"pricing_detected:{reason}" for reason in reasons] if pricing_hit else []

    parse_result = parse_tender_requirements(full_text)
    insights = _insights_from_parsed_requirements(parse_result.requirements)
    if not insights:
        for page in pages:
            for line, anchor in _extract_lines(page_no=page.page_no, text=page.text or ""):
                insights.extend(_classify_line(content=line, page_no=page.page_no, section_anchor=anchor))
        insights = _dedupe(insights)
    if parse_result.status != "OK":
        warnings.append("tender_parse_need_human_input")
    status = "SUCCEEDED" if insights else "NEED_HUMAN_INPUT"

    if not insights:
        warnings.append("no_structured_key_points_detected")

    summary = _summary(insights, warnings)
    storage_path = _save_file(filename, content)

    try:
        with session_scope() as db:
            source_doc = Document(
                project_id=project_uuid,
                kind=DocKind.TENDER,
                filename=filename,
                content_type="application/pdf",
                object_uri=str(storage_path),
                sha256=hashlib.sha256(content).hexdigest(),
                page_count=len(pages),
                language="zh-CN",
                sensitivity=SensitivityLevel.PUBLIC_OK,
                created_by=created_by,
            )
            db.add(source_doc)
            db.flush()

            run = TenderAnalysisRun(
                project_id=project_uuid,
                document_id=source_doc.id,
                filename=filename,
                status=status,
                summary_json=summary.model_dump(mode="json"),
                created_by=created_by,
            )
            db.add(run)
            db.flush()

            for item in insights:
                db.add(
                    TenderKeyInfo(
                        run_id=run.id,
                        project_id=project_uuid,
                        document_id=source_doc.id,
                        category=item.category,
                        title=_item_title(item),
                        content=item.content,
                        page_no=item.page_no,
                        section_anchor=item.section_anchor,
                        score_weight=item.score_weight,
                        is_must=item.is_must,
                        importance=item.importance,
                        source_quote=item.content[:160],
                    )
                )
            db.commit()
            run_item = TenderAnalysisRunItem(
                run_id=str(run.id),
                project_id=str(project_uuid) if project_uuid else None,
                document_id=str(source_doc.id),
                filename=filename,
                status=status,
                created_at=run.created_at.isoformat() if run.created_at else datetime.now(UTC).isoformat(),
            )
            return run_item, summary
    except SQLAlchemyError as exc:
        raise RuntimeError(f"failed to persist tender analysis: {exc}") from exc


def list_tender_analysis_runs(project_id: str | None, limit: int = 50) -> list[TenderAnalysisRunItem]:
    project_uuid = _parse_project_uuid(project_id)
    with session_scope() as db:
        stmt = select(TenderAnalysisRun).order_by(TenderAnalysisRun.created_at.desc()).limit(max(1, min(limit, 200)))
        if project_uuid:
            stmt = stmt.where(TenderAnalysisRun.project_id == project_uuid)
        runs = db.execute(stmt).scalars().all()
        return [
            TenderAnalysisRunItem(
                run_id=str(run.id),
                project_id=str(run.project_id) if run.project_id else None,
                document_id=str(run.document_id) if run.document_id else None,
                filename=run.filename,
                status=run.status,
                created_at=run.created_at.isoformat() if run.created_at else "",
            )
            for run in runs
        ]


def get_tender_analysis_detail(run_id: str) -> TenderAnalysisDetailResponse:
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError as exc:
        raise ValueError("invalid run_id") from exc

    with session_scope() as db:
        run = db.execute(select(TenderAnalysisRun).where(TenderAnalysisRun.id == run_uuid)).scalar_one_or_none()
        if not run:
            raise ValueError("analysis run not found")
        key_infos = db.execute(
            select(TenderKeyInfo)
            .where(TenderKeyInfo.run_id == run_uuid)
            .order_by(TenderKeyInfo.importance.desc(), TenderKeyInfo.page_no.asc())
        ).scalars().all()

        summary_payload = run.summary_json or {}
        summary = TenderAnalysisSummary(
            total_items=int(summary_payload.get("total_items", 0)),
            category_counts=dict(summary_payload.get("category_counts", {})),
            key_sections=list(summary_payload.get("key_sections", [])),
            warnings=list(summary_payload.get("warnings", [])),
        )
        run_item = TenderAnalysisRunItem(
            run_id=str(run.id),
            project_id=str(run.project_id) if run.project_id else None,
            document_id=str(run.document_id) if run.document_id else None,
            filename=run.filename,
            status=run.status,
            created_at=run.created_at.isoformat() if run.created_at else "",
        )
        items = [
            TenderKeyInfoItem(
                id=str(item.id),
                category=item.category.value if hasattr(item.category, "value") else str(item.category),
                title=item.title,
                content=item.content,
                page_no=item.page_no,
                section_anchor=item.section_anchor,
                score_weight=float(item.score_weight) if item.score_weight is not None else None,
                is_must=bool(item.is_must),
                importance=int(item.importance or 50),
            )
            for item in key_infos
        ]
        return TenderAnalysisDetailResponse(run=run_item, summary=summary, key_infos=items)
