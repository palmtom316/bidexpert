from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import (
    OutlineConfirmRequest,
    OutlineCreateRequest,
    SectionConfirmRequest,
    WorkflowSectionRequest,
)


def test_section_generation_requires_confirmed_outline() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-sec-1", tender_text="第一章 总则。必须满足合规要求。")
    )
    payload = WorkflowSectionRequest(
        outline_id=created.outline_id,
        project_id="p-sec-1",
        section_key="S-001",
        section_title="第一章 总则",
        requirement_texts=["必须满足合规要求"],
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.enqueue_section_workflow(payload)

    assert exc_info.value.status_code == 400


def test_section_generation_allowed_after_outline_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Chain:
        def apply_async(self) -> object:
            return type("R", (), {"id": "task-demo"})()

    monkeypatch.setattr(routes, "chain", lambda *_args, **_kwargs: _Chain())

    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-sec-2", tender_text="第二章 技术规范。应当满足施工方案。")
    )
    routes.confirm_outline(OutlineConfirmRequest(outline_id=created.outline_id, approved=True))

    payload = WorkflowSectionRequest(
        outline_id=created.outline_id,
        project_id="p-sec-2",
        section_key="S-001",
        section_title="第二章 技术规范",
        requirement_texts=["应当满足施工方案"],
    )
    result = routes.enqueue_section_workflow(payload)

    assert result.status == "PENDING"
    assert result.section_key == "S-001"
    assert result.task_ids["SECTION_PIPELINE"] == "task-demo"


def test_section_confirm_marks_user_approved() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-sec-3", tender_text="第三章 施工组织。必须满足进度要求。")
    )
    routes.confirm_outline(OutlineConfirmRequest(outline_id=created.outline_id, approved=True))
    result = routes.confirm_section(
        SectionConfirmRequest(outline_id=created.outline_id, section_key="S-001", approved=True)
    )

    assert result.status == "SECTION_CONFIRMED"
    assert result.section_key == "S-001"
