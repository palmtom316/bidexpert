from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import (
    OutlineConfirmRequest,
    OutlineCreateRequest,
    SectionConfirmRequest,
    SectionFeedbackUpsertRequest,
)


def test_feedback_requires_confirmed_section() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-fb-1", tender_text="第一章 总则。必须满足资质。")
    )
    routes.confirm_outline(OutlineConfirmRequest(outline_id=created.outline_id, approved=True))

    with pytest.raises(HTTPException) as exc_info:
        routes.feedback_upsert_section(
            SectionFeedbackUpsertRequest(
                outline_id=created.outline_id,
                section_key="S-001",
                section_title="第一章 总则",
                expert_doc_id="exp-1",
                content_md="本章内容",
            )
        )

    assert exc_info.value.status_code == 400


def test_feedback_upsert_builds_standardized_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Task:
        @staticmethod
        def delay(expert_doc_id: str, chunks: list[dict]) -> object:
            captured["expert_doc_id"] = expert_doc_id
            captured["chunks"] = chunks
            return type("R", (), {"id": "task-fb-1"})()

    monkeypatch.setattr(routes, "upsert_evidence_task", _Task)

    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-fb-2", tender_text="第二章 技术规范。应当满足质量要求。")
    )
    routes.confirm_outline(OutlineConfirmRequest(outline_id=created.outline_id, approved=True))
    routes.confirm_section(
        SectionConfirmRequest(outline_id=created.outline_id, section_key="S-001", approved=True)
    )

    result = routes.feedback_upsert_section(
        SectionFeedbackUpsertRequest(
            outline_id=created.outline_id,
            section_key="S-001",
            section_title="第二章 技术规范",
            expert_doc_id="exp-2",
            content_md="第一段经验。\n\n第二段做法。",
            industry_tag="construction",
        )
    )

    assert result.task_id == "task-fb-1"
    assert result.status == "PENDING"
    assert captured["expert_doc_id"] == "exp-2"
    chunks = captured["chunks"]
    assert isinstance(chunks, list)
    assert len(chunks) == 2
    assert chunks[0]["doc_type"] == "SECTION_FEEDBACK"
    assert chunks[0]["industry_tag"] == "construction"
    assert chunks[0]["source_locator"]["outline_id"] == created.outline_id
    assert chunks[0]["source_locator"]["section_key"] == "S-001"
