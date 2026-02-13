from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import uuid

from app.core.config import settings
from app.schemas.contracts import EvidenceSearchHit, EvidenceUpsertItem
from app.services.embedding import embed_text


@dataclass
class RetrievedEvidence:
    chunk_id: str
    score: float
    text: str
    payload: dict


def _is_payload_allowed(payload: dict) -> bool:
    sensitivity = payload.get("sensitivity_level", "PUBLIC_OK")
    if sensitivity != "PUBLIC_OK":
        return False

    forbidden = set(payload.get("forbidden_tags", []) or [])
    if "PRICING_RELATED" in forbidden:
        return False

    valid_to = payload.get("valid_to")
    if valid_to and valid_to < date.today().isoformat():
        return False

    return True


class QdrantStore:
    def __init__(self) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams

        self.client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
        self.collection = settings.qdrant_collection
        self.vector_size = settings.qdrant_vector_size

        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection for c in collections)
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def upsert_chunks(self, expert_doc_id: str, chunks: list[EvidenceUpsertItem]) -> int:
        from qdrant_client.http.models import PointStruct

        points: list[PointStruct] = []
        for chunk in chunks:
            payload = {
                "expert_doc_id": expert_doc_id,
                "chunk_id": chunk.chunk_id,
                "doc_type": chunk.doc_type,
                "section_type": chunk.section_type,
                "industry_tag": chunk.industry_tag,
                "sensitivity_level": chunk.sensitivity_level,
                "valid_to": chunk.valid_to,
                "forbidden_tags": chunk.forbidden_tags,
                "quality_score": chunk.quality_score,
                "source_locator": chunk.source_locator,
                "text": chunk.text,
            }
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc_id}:{chunk.chunk_id}")),
                    vector=embed_text(chunk.text, self.vector_size),
                    payload=payload,
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)

    def search(self, query: str, top_k: int = 5, industry_tag: str | None = None) -> list[RetrievedEvidence]:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        must = [FieldCondition(key="sensitivity_level", match=MatchValue(value="PUBLIC_OK"))]
        if industry_tag:
            must.append(FieldCondition(key="industry_tag", match=MatchValue(value=industry_tag)))

        must_not = [FieldCondition(key="forbidden_tags", match=MatchValue(value="PRICING_RELATED"))]

        query_filter = Filter(must=must, must_not=must_not)
        query_vector = embed_text(query, self.vector_size)
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k * 2,
                with_payload=True,
                with_vectors=False,
            )
            hits = getattr(response, "points", [])
        else:
            hits = self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=top_k * 2,
                with_payload=True,
                with_vectors=False,
            )

        items: list[RetrievedEvidence] = []
        for hit in hits:
            payload = hit.payload or {}
            if not _is_payload_allowed(payload):
                continue
            items.append(
                RetrievedEvidence(
                    chunk_id=str(payload.get("chunk_id", hit.id)),
                    score=float(hit.score),
                    text=str(payload.get("text", "")),
                    payload=payload,
                )
            )
            if len(items) >= top_k:
                break
        return items


def to_search_hits(items: list[RetrievedEvidence]) -> list[EvidenceSearchHit]:
    return [
        EvidenceSearchHit(chunk_id=i.chunk_id, score=i.score, text=i.text, payload=i.payload)
        for i in items
    ]
