from __future__ import annotations

from types import SimpleNamespace

from app.services import qdrant_store


class _DummyClient:
    def __init__(self) -> None:
        self.upsert_args = None
        self.query_args = None

    def upsert(self, *, collection_name, points, wait):  # noqa: ANN001
        self.upsert_args = {
            "collection_name": collection_name,
            "points": list(points),
            "wait": wait,
        }

    def query_points(self, **kwargs):  # noqa: ANN001
        self.query_args = kwargs
        point = SimpleNamespace(
            id="MSNIP-2026-TEST0001",
            score=0.88,
            payload={
                "snippet_id": "MSNIP-2026-TEST0001",
                "template_md": "### 模板\n1. 示例",
                "review_status": "approved",
                "risk_level": "low",
            },
        )
        return SimpleNamespace(points=[point])


def test_upsert_methodology_snippet_writes_payload(monkeypatch) -> None:
    store = object.__new__(qdrant_store.QdrantStore)
    store.client = _DummyClient()
    store.methodology_collection = "kb_methodology"
    store.vector_size = 4
    store._ensure_dense_collection = lambda _name: None

    monkeypatch.setattr(
        qdrant_store,
        "resolve_profile_for_task",
        lambda **_: SimpleNamespace(
            provider="openai",
            model="text-embedding-3-large",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        ),
    )
    monkeypatch.setattr(qdrant_store, "embed_text", lambda *args, **kwargs: [0.1, 0.2, 0.3, 0.4])  # noqa: ARG005

    store.upsert_methodology_snippet(
        snippet_id="MSNIP-2026-TEST0001",
        title="进度保障",
        domain="配网",
        tags=["进度"],
        applicability={"region": ["通用"]},
        template_md="### 模板\n1. 示例",
        risk_level="low",
        review_status="approved",
        source_type="public_doc",
    )

    assert store.client.upsert_args is not None
    assert store.client.upsert_args["collection_name"] == "kb_methodology"
    payload = getattr(store.client.upsert_args["points"][0], "payload", {})
    assert payload["review_status"] == "approved"
    assert payload["risk_level"] == "low"
    assert payload["snippet_id"] == "MSNIP-2026-TEST0001"


def test_search_methodology_enforces_review_and_risk_filter(monkeypatch) -> None:
    store = object.__new__(qdrant_store.QdrantStore)
    store.client = _DummyClient()
    store.methodology_collection = "kb_methodology"
    store.vector_size = 4
    store._ensure_dense_collection = lambda _name: None

    monkeypatch.setattr(
        qdrant_store,
        "resolve_profile_for_task",
        lambda **_: SimpleNamespace(
            provider="openai",
            model="text-embedding-3-large",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        ),
    )
    monkeypatch.setattr(qdrant_store, "embed_text", lambda *args, **kwargs: [0.1, 0.2, 0.3, 0.4])  # noqa: ARG005

    hits = store.search_methodology(query="进度", top_k=3, domain="配网")

    assert len(hits) == 1
    assert hits[0].snippet_id == "MSNIP-2026-TEST0001"

    query_filter = store.client.query_args["query_filter"]
    must = list(getattr(query_filter, "must", []))
    must_not = list(getattr(query_filter, "must_not", []))

    assert any(
        getattr(condition, "key", None) == "review_status"
        and getattr(getattr(condition, "match", None), "value", None) == "approved"
        for condition in must
    )
    assert any(
        getattr(condition, "key", None) == "risk_level"
        and getattr(getattr(condition, "match", None), "value", None) == "high"
        for condition in must_not
    )
