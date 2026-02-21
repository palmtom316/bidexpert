from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import inspect, text

from app.db.session import session_scope, engine
from app.extract.tender_parser import parse_tender_requirements
from app.models.tables import WorkflowRun
from app.schemas.contracts import OutlineSection

_DEFAULT_STEP = "G1"


def _ensure_table() -> None:
    WorkflowRun.__table__.create(bind=engine, checkfirst=True)
    inspector = inspect(engine)
    columns = {item["name"] for item in inspector.get_columns("workflow_run")}
    statements: list[str] = []
    if "current_step" not in columns:
        statements.append("ALTER TABLE workflow_run ADD COLUMN current_step TEXT DEFAULT 'G0'")
    if "step_status" not in columns:
        statements.append("ALTER TABLE workflow_run ADD COLUMN step_status TEXT DEFAULT 'paused'")
    if "resume_from_step" not in columns:
        statements.append("ALTER TABLE workflow_run ADD COLUMN resume_from_step TEXT DEFAULT 'G1'")
    if "retry_count" not in columns:
        statements.append("ALTER TABLE workflow_run ADD COLUMN retry_count INTEGER DEFAULT 0")
    if "last_error" not in columns:
        statements.append("ALTER TABLE workflow_run ADD COLUMN last_error TEXT")
    if statements:
        with engine.begin() as conn:
            for sql in statements:
                conn.execute(text(sql))


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
    with session_scope() as db:
        db.add(
            WorkflowRun(
                id=outline_id,
                project_id=project_id,
                status="OUTLINE_PENDING_CONFIRM",
                sections_json={"sections": [item.model_dump() for item in sections]},
                section_status_json={},
                current_step="G0",
                step_status="paused",
                resume_from_step=_DEFAULT_STEP,
                retry_count=0,
                last_error=None,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return outline_id, sections, "OUTLINE_PENDING_CONFIRM"


def confirm_outline_run(outline_id: str, approved: bool) -> str:
    _ensure_table()
    with session_scope() as db:
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
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).first()
        if not run:
            return None
        return str(run.status)


def mark_section_pending(outline_id: str, section_key: str) -> None:
    _ensure_table()
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        section_status = dict(run.section_status_json or {})
        section_status[section_key] = "SECTION_PENDING_CONFIRM"
        run.section_status_json = section_status
        run.current_step = "G0"
        run.step_status = "generating"
        run.resume_from_step = _DEFAULT_STEP
        run.last_error = None
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()


def confirm_section_run(outline_id: str, section_key: str, approved: bool) -> str:
    _ensure_table()
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        section_status = dict(run.section_status_json or {})
        section_status[section_key] = "SECTION_CONFIRMED" if approved else "SECTION_REJECTED"
        run.section_status_json = section_status
        if approved:
            run.current_step = "G5"
            run.step_status = "paused"
            run.resume_from_step = "G5"
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()
        return str(section_status[section_key])


def get_section_status(outline_id: str, section_key: str) -> str | None:
    _ensure_table()
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).first()
        if not run:
            return None
        section_status = dict(run.section_status_json or {})
        value = section_status.get(section_key)
        return str(value) if value else None


def update_run_progress(
    *,
    outline_id: str,
    current_step: str,
    step_status: str,
    resume_from_step: str | None = None,
    last_error: str | None = None,
    retry_increment: int = 0,
) -> None:
    _ensure_table()
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).with_for_update().first()
        if not run:
            raise ValueError("outline not found")
        run.current_step = current_step
        run.step_status = step_status
        if resume_from_step is not None:
            run.resume_from_step = resume_from_step
        if last_error is not None:
            run.last_error = last_error
        if retry_increment > 0:
            run.retry_count = int(run.retry_count or 0) + retry_increment
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()


def get_resume_from_step(outline_id: str) -> str:
    _ensure_table()
    with session_scope() as db:
        run = db.query(WorkflowRun).filter(WorkflowRun.id == outline_id).first()
        if not run:
            raise ValueError("outline not found")
        value = str(run.resume_from_step or "").strip()
        return value or _DEFAULT_STEP
