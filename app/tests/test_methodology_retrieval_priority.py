from __future__ import annotations

from types import SimpleNamespace

from app.rag import rag_flow
from app.services.qdrant_store import RetrievedEvidence


class _DummyStore:
    def search_methodology(self, *, query: str, top_k: int, domain: str | None):  # noqa: ARG002
        return [
            SimpleNamespace(
                snippet_id="MSNIP-2026-ABCDEF01",
                score=0.91,
                text="### 方法论模板（通用）\n1. 优先保障关键路径。",
                payload={
                    "snippet_id": "MSNIP-2026-ABCDEF01",
                    "review_status": "approved",
                    "risk_level": "low",
                },
            )
        ]

    def search(self, *, query: str, top_k: int, industry_tag: str | None, project_id: str | None):  # noqa: ARG002
        return [
            RetrievedEvidence(
                chunk_id="history-001",
                score=0.74,
                text="历史标书表达",
                payload={"kb_source": "expert_chunks_v1"},
            )
        ]


def test_methodology_retrieval_has_priority(monkeypatch) -> None:
    monkeypatch.setattr(rag_flow, "get_qdrant_store", lambda: _DummyStore())
    monkeypatch.setattr(
        rag_flow,
        "resolve_profile_for_task",
        lambda **_: SimpleNamespace(provider="openai", model="gpt-5", api_key=None, base_url=None),
    )
    monkeypatch.setattr(
        rag_flow,
        "rewrite_query_with_profile",
        lambda **kwargs: SimpleNamespace(rewritten_query=kwargs["query"]),
    )

    retrieval, logs = rag_flow.retrieve_for_subrequirements(
        sub_requirements=[rag_flow.SubRequirement(sub_id="sub-1", description="进度保障", category="GENERAL")],
        top_k=4,
        industry_tag="配网",
        project_id="p-1",
    )

    hits = retrieval["sub-1"]
    assert len(hits) == 2
    assert hits[0].payload["kb_source"] == "kb_methodology"
    assert hits[1].chunk_id == "history-001"
    assert logs[0]["hit_ids"][0] == "MSNIP-2026-ABCDEF01"
