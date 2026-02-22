from __future__ import annotations

from types import SimpleNamespace

from app.schemas.contracts import EvidenceUpsertItem
from app.services import qdrant_store
from app.services.qdrant_store import RetrievedEvidence, _rerank_hits


def test_rerank_hits_promotes_lexical_match() -> None:
    hits = [
        RetrievedEvidence(
            chunk_id="a",
            score=0.95,
            text="本公司具备丰富项目经验与实施能力。",
            payload={"quality_score": 70.0},
        ),
        RetrievedEvidence(
            chunk_id="b",
            score=0.60,
            text="已提供资质证明、许可证和认证证书原件。",
            payload={"quality_score": 92.0},
        ),
    ]

    reranked = _rerank_hits(query="资质证明", items=hits, top_k=2)
    assert reranked[0].chunk_id == "b"
    assert len(reranked) == 2


def test_build_query_filter_includes_project_id_for_isolation() -> None:
    store = object.__new__(qdrant_store.QdrantStore)
    query_filter = store._build_query_filter(industry_tag="政企", project_id="project-a")

    must = list(getattr(query_filter, "must", []))
    assert any(
        getattr(condition, "key", None) == "project_id"
        and getattr(getattr(condition, "match", None), "value", None) == "project-a"
        for condition in must
    )


def test_upsert_chunks_persists_project_id_in_payload(monkeypatch) -> None:
    class _DummyClient:
        def __init__(self) -> None:
            self.points = []
            self.collection_name = None
            self.wait = None

        def upsert(self, *, collection_name, points, wait) -> None:  # noqa: ANN001
            self.collection_name = collection_name
            self.points = list(points)
            self.wait = wait

    store = object.__new__(qdrant_store.QdrantStore)
    store.client = _DummyClient()
    store.collection = "expert_chunks_v1"
    store.vector_size = 4
    store._sparse_enabled = False

    monkeypatch.setattr(
        qdrant_store,
        "resolve_profile_for_task",
        lambda **_: SimpleNamespace(
            profile_id=None,
            provider="openai",
            model="text-embedding-3-large",
            api_key="sk-test",
            base_url="https://api.openai.com/v1",
        ),
    )
    monkeypatch.setattr(
        qdrant_store,
        "embed_text",
        lambda *args, **kwargs: [0.1, 0.2, 0.3, 0.4],  # noqa: ARG005
    )

    chunk = EvidenceUpsertItem(
        chunk_id="chunk-1",
        text="示例证据文本",
        source_locator={"doc_id": "doc-1"},
    )
    written = store.upsert_chunks(
        expert_doc_id="expert-doc-1",
        chunks=[chunk],
        project_id="project-a",
    )

    assert written == 1
    assert store.client.collection_name == "expert_chunks_v1"
    payload = getattr(store.client.points[0], "payload", {})
    assert payload.get("project_id") == "project-a"
