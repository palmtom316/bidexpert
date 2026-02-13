from __future__ import annotations

from app.api import routes
from app.schemas.contracts import OutlineConfirmRequest, OutlineCreateRequest


def test_create_outline_returns_pending_confirmation() -> None:
    payload = OutlineCreateRequest(project_id="p-001", tender_text="第一章 总则。必须具备资质。")
    result = routes.create_outline(payload)

    assert result.status == "OUTLINE_PENDING_CONFIRM"
    assert result.outline_id
    assert len(result.sections) >= 1


def test_confirm_outline_marks_confirmed() -> None:
    create_payload = OutlineCreateRequest(project_id="p-002", tender_text="第二章 技术要求。应当满足。")
    created = routes.create_outline(create_payload)

    confirm_payload = OutlineConfirmRequest(outline_id=created.outline_id, approved=True)
    confirmed = routes.confirm_outline(confirm_payload)

    assert confirmed.status == "OUTLINE_CONFIRMED"
    assert confirmed.outline_id == created.outline_id
