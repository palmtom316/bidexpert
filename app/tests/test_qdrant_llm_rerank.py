from __future__ import annotations

from types import SimpleNamespace

import httpx

from app.services import qdrant_store
from app.services.qdrant_store import RetrievedEvidence


def test_llm_rerank_reorders_by_ranked_chunk_ids(monkeypatch) -> None:
    items = [
        RetrievedEvidence(chunk_id="c1", score=0.9, text="第一段文本", payload={}),
        RetrievedEvidence(chunk_id="c2", score=0.8, text="第二段文本", payload={}),
        RetrievedEvidence(chunk_id="c3", score=0.7, text="第三段文本", payload={}),
    ]

    monkeypatch.setattr(
        qdrant_store,
        "resolve_profile_for_task",
        lambda **_: SimpleNamespace(
            profile_id="profile-rerank",
            provider="qwen",
            model="qwen3.5",
            api_key="sk-123",
            base_url="https://example.ai/v1",
        ),
    )

    class _Resp:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"ranked_chunk_ids":["c2","c1"]}',
                        }
                    }
                ]
            }

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _Resp())

    reranked = qdrant_store._llm_rerank_hits(  # noqa: SLF001
        query="资质要求",
        items=items,
        top_k=2,
        project_id="proj-1",
    )
    assert [item.chunk_id for item in reranked] == ["c2", "c1"]


def test_optional_llm_rerank_falls_back_when_llm_fails(monkeypatch) -> None:
    items = [
        RetrievedEvidence(chunk_id="a", score=0.9, text="A", payload={}),
        RetrievedEvidence(chunk_id="b", score=0.8, text="B", payload={}),
    ]

    monkeypatch.setattr(qdrant_store.settings, "qdrant_llm_rerank_enabled", True, raising=False)
    monkeypatch.setattr(
        qdrant_store,
        "_llm_rerank_hits",
        lambda **_: (_ for _ in ()).throw(RuntimeError("llm down")),
    )
    monkeypatch.setattr(
        qdrant_store,
        "_cross_encoder_rerank_hits",
        lambda **_: [items[1], items[0]],
    )

    reranked = qdrant_store._rerank_hits_with_optional_llm(  # noqa: SLF001
        query="测试",
        items=items,
        top_k=2,
        project_id="proj-1",
    )
    assert [item.chunk_id for item in reranked] == ["b", "a"]
