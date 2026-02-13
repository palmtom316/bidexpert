from __future__ import annotations

from app.api import routes
from app.db.session import SessionLocal
from app.models.tables import WorkflowRun
from app.schemas.contracts import OutlineConfirmRequest, OutlineCreateRequest


def test_outline_create_persists_workflow_run_row() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-db-1", tender_text="第一章 总则。必须满足资质。")
    )

    with SessionLocal() as db:
        row = db.query(WorkflowRun).filter(WorkflowRun.id == created.outline_id).first()

    assert row is not None
    assert row.project_id == "p-db-1"
    assert row.status == "OUTLINE_PENDING_CONFIRM"


def test_outline_confirm_updates_persisted_status() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-db-2", tender_text="第二章 技术规范。应当提供组织方案。")
    )
    routes.confirm_outline(OutlineConfirmRequest(outline_id=created.outline_id, approved=True))

    with SessionLocal() as db:
        row = db.query(WorkflowRun).filter(WorkflowRun.id == created.outline_id).first()

    assert row is not None
    assert row.status == "OUTLINE_CONFIRMED"
