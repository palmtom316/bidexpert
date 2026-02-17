from __future__ import annotations

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

