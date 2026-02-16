from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from app.db.session import SessionLocal, engine
from app.extract.tender_parser import parse_tender_requirements
from app.models.tables import WorkflowRun
from app.schemas.contracts import OutlineSection


def _ensure_table() -> None:
    WorkflowRun.__table__.create(bind=engine, checkfirst=True)


def _build_outline_sections(tender_text: str) -> list[OutlineSection]:
    parsed = parse_tender_requirements(tender_text)
    grouped: dict[str, list[str]] = {}
    for item in parsed.requirements:
        title = item.section_anchor or "未分类章节"
        grouped.setdefault(title, []).append(item.original_text)

    if not grouped:
        return [OutlineSection(section_key="S-001", section_title="未分类章节", requirement_texts=[tender_text[:200]])]

    sections: list[OutlineSection] = []
    for index, (title, reqs) in enumerate(grouped.items(), start=1):
        sections.append(
            OutlineSection(
                section_key=f"S-{index:03d}",
                section_title=title,
                requirement_texts=reqs,
            )
        )
    return sections


def create_outline_run(project_id: str, tender_text: str) -> tuple[str, list[OutlineSection], str]:
    _ensure_table()
    outline_id = str(uuid4())
    sections = _build_outline_sections(tender_text)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            WorkflowRun(
                id=outline_id,
                project_id=project_id,
                status="OUTLINE_PENDING_CONFIRM",
                sections_json={"sections": [item.model_dump() for item in sections]},
                section_status_json={},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return outline_id, sections, "OUTLINE_PENDING_CONFIRM"


def confirm_outline_run(outline_id: str, approved: bool) -> str:
    _ensure_table()
    with SessionLocal() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        run.status = "OUTLINE_CONFIRMED" if approved else "OUTLINE_REJECTED"
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        return str(run.status)


def get_outline_status(outline_id: str) -> str | None:
    _ensure_table()
    with SessionLocal() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).first()
        if not run:
            return None
        return str(run.status)


def mark_section_pending(outline_id: str, section_key: str) -> None:
    _ensure_table()
    with SessionLocal() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        section_status = dict(run.section_status_json or {})
        section_status[section_key] = "SECTION_PENDING_CONFIRM"
        run.section_status_json = section_status
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()


def confirm_section_run(outline_id: str, section_key: str, approved: bool) -> str:
    _ensure_table()
    with SessionLocal() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        section_status = dict(run.section_status_json or {})
        section_status[section_key] = "SECTION_CONFIRMED" if approved else "SECTION_REJECTED"
        run.section_status_json = section_status
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        return str(section_status[section_key])


def get_section_status(outline_id: str, section_key: str) -> str | None:
    _ensure_table()
    with SessionLocal() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).first()
        if not run:
            return None
        section_status = dict(run.section_status_json or {})
        value = section_status.get(section_key)
        return str(value) if value else None
