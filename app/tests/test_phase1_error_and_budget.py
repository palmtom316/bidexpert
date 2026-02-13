from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import DraftGenerationRequest, EvidenceSearchRequest, EvidenceUpsertItem, EvidenceUpsertRequest
from app.services import llm_audit


def test_generate_draft_maps_value_error_to_400(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_value_error(**_: object) -> object:
        raise ValueError("bad requirement")

    monkeypatch.setattr(routes, "generate_draft_with_retrieval", _raise_value_error)

    payload = DraftGenerationRequest(requirement_id="REQ-1", requirement_text="text")
    with pytest.raises(HTTPException) as exc_info:
        routes.generate_draft(payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "bad requirement"


def test_evidence_search_maps_runtime_error_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Store:
        def search(self, **_: object) -> list[object]:
            raise RuntimeError("qdrant unavailable")

    monkeypatch.setattr(routes, "QdrantStore", _Store)

    with pytest.raises(HTTPException) as exc_info:
        routes.evidence_search(EvidenceSearchRequest(query="q"))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "service temporarily unavailable"


def test_evidence_upsert_maps_runtime_error_to_503(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Task:
        @staticmethod
        def delay(*_: object) -> object:
            raise RuntimeError("queue down")

    monkeypatch.setattr(routes, "upsert_evidence_task", _Task)

    payload = EvidenceUpsertRequest(
        expert_doc_id="doc-1",
        chunks=[EvidenceUpsertItem(chunk_id="c1", text="t1")],
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.evidence_upsert(payload)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "service temporarily unavailable"


def test_reserve_budget_persistent_uses_row_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Result:
        def __init__(self, project: object) -> None:
            self._project = project

        def scalar_one_or_none(self) -> object:
            return self._project

    class _Project:
        def __init__(self) -> None:
            self.token_budget_total = 100
            self.token_budget_used = 10

    class _Session:
        def __init__(self, project: object) -> None:
            self._project = project
            self.stmt = None
            self.committed = False
            self.added = False

        def __enter__(self) -> "_Session":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def execute(self, stmt: object) -> _Result:
            self.stmt = stmt
            return _Result(self._project)

        def add(self, _: object) -> None:
            self.added = True

        def commit(self) -> None:
            self.committed = True

    project = _Project()
    session = _Session(project)

    monkeypatch.setattr(llm_audit, "SessionLocal", lambda: session)

    ok, remaining = llm_audit.reserve_budget_persistent(str(uuid.uuid4()), 20)

    assert ok is True
    assert remaining == 70
    assert project.token_budget_used == 30
    assert session.added is True
    assert session.committed is True
    assert getattr(session.stmt, "_for_update_arg", None) is not None
