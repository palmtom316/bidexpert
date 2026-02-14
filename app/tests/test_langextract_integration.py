from __future__ import annotations

import pytest

from app.api import routes
from app.schemas.contracts import HistoricalExtractRequest
from app.services import historical_extractor


def test_extract_evidence_chunks_maps_langextract_output(monkeypatch: pytest.MonkeyPatch) -> None:
    def _fake_run(*_: object, **__: object) -> list[dict[str, object]]:
        return [
            {
                "extraction_class": "资质要求",
                "extraction_text": "投标人须具备ISO9001认证",
                "attributes": {"section_anchor": "第一章 总则"},
            },
            {
                "extraction_class": "业绩要求",
                "extraction_text": "近三年完成不少于5个同类项目",
                "attributes": {},
            },
        ]

    monkeypatch.setattr(historical_extractor, "_run_langextract", _fake_run)

    chunks = historical_extractor.extract_evidence_chunks_from_text(
        text="示例文本",
        industry_tag="construction",
        doc_type="EXPERT_HISTORY",
    )

    assert len(chunks) == 2
    assert chunks[0].text == "投标人须具备ISO9001认证"
    assert chunks[0].industry_tag == "construction"
    assert chunks[0].section_type == "资质要求"
    assert chunks[0].source_locator == {"section_anchor": "第一章 总则"}
    assert chunks[1].chunk_id.startswith("lx-")


def test_extract_evidence_chunks_rejects_blank_text() -> None:
    with pytest.raises(ValueError):
        historical_extractor.extract_evidence_chunks_from_text(text="  ")


def test_evidence_extract_upsert_enqueues_task(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _Task:
        @staticmethod
        def delay(
            expert_doc_id: str,
            text: str,
            industry_tag: str | None,
            model_id: str | None,
        ) -> object:
            captured["expert_doc_id"] = expert_doc_id
            captured["text"] = text
            captured["industry_tag"] = industry_tag
            captured["model_id"] = model_id
            return type("R", (), {"id": "task-123"})()

    monkeypatch.setattr(routes, "extract_upsert_historical_task", _Task)

    payload = HistoricalExtractRequest(
        expert_doc_id="doc-h-1",
        text="招标文件历史样本",
        industry_tag="construction",
        model_id="gemini-2.5-pro",
    )
    result = routes.evidence_extract_upsert(payload)

    assert result.task_id == "task-123"
    assert result.status == "PENDING"
    assert captured == {
        "expert_doc_id": "doc-h-1",
        "text": "招标文件历史样本",
        "industry_tag": "construction",
        "model_id": "gemini-2.5-pro",
    }
