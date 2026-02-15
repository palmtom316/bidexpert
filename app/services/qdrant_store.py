from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.core.config import settings
from app.schemas.contracts import EvidenceSearchHit, EvidenceUpsertItem
from app.services.byok import resolve_profile_for_task
from app.services.embedding import embed_text

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


@dataclass
class RetrievedEvidence:
    chunk_id: str
    score: float
    text: str
    payload: dict


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall((text or "").lower())


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

    def upsert_chunks(self, expert_doc_id: str, chunks: list[EvidenceUpsertItem], project_id: str | None = None) -> int:
        from qdrant_client.http.models import PointStruct

        embed_profile = resolve_profile_for_task(project_id=project_id, task_type="EMBED")
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
                "embed_provider": embed_profile.provider,
                "embed_model": embed_profile.model,
            }
            points.append(
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc_id}:{chunk.chunk_id}")),
                    vector=embed_text(
                        chunk.text,
                        self.vector_size,
                        model_id=embed_profile.model,
                        provider=embed_profile.provider,
                        api_key=embed_profile.api_key,
                        base_url=embed_profile.base_url,
                        project_id=project_id,
                    ),
                    payload=payload,
                )
            )

        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)

    def _build_query_filter(self, industry_tag: str | None = None):
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue

        must = [FieldCondition(key="sensitivity_level", match=MatchValue(value="PUBLIC_OK"))]
        if industry_tag:
            must.append(FieldCondition(key="industry_tag", match=MatchValue(value=industry_tag)))
        must_not = [FieldCondition(key="forbidden_tags", match=MatchValue(value="PRICING_RELATED"))]
        return Filter(must=must, must_not=must_not)

    def _vector_search(self, query_vector: list[float], query_filter, limit: int):
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection,
                query=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            return list(getattr(response, "points", []))
        return list(
            self.client.search(
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        )

    def _bm25_scores(self, query: str, query_filter, limit: int) -> list[tuple[object, float]]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        points, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=query_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            return []

        docs_tokens: list[list[str]] = []
        valid_points: list[object] = []
        for point in points:
            payload = getattr(point, "payload", None) or {}
            text = str(payload.get("text", ""))
            tokens = _tokenize(text)
            if not tokens:
                continue
            valid_points.append(point)
            docs_tokens.append(tokens)

        if not valid_points:
            return []

        doc_count = len(docs_tokens)
        avg_doc_len = max(1.0, sum(len(tokens) for tokens in docs_tokens) / doc_count)
        query_vocab = set(query_terms)
        df = Counter()
        for tokens in docs_tokens:
            token_set = set(tokens)
            for term in query_vocab:
                if term in token_set:
                    df[term] += 1

        k1 = 1.2
        b = 0.75
        scored: list[tuple[object, float]] = []
        for idx, point in enumerate(valid_points):
            tokens = docs_tokens[idx]
            tf = Counter(tokens)
            dl = len(tokens)
            score = 0.0
            for term in query_vocab:
                freq = tf.get(term, 0)
                if freq <= 0:
                    continue
                denom = df.get(term, 0) + 0.5
                idf = math.log(1 + (doc_count - df.get(term, 0) + 0.5) / denom)
                score += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avg_doc_len))
            if score > 0:
                scored.append((point, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        return scored

    def _chunk_id(self, point: object) -> str:
        payload = getattr(point, "payload", None) or {}
        return str(payload.get("chunk_id", getattr(point, "id", "")))

    def _fuse_hybrid(
        self,
        *,
        vector_hits: list[object],
        bm25_hits: list[tuple[object, float]],
        top_k: int,
    ) -> list[RetrievedEvidence]:
        candidates: dict[str, dict] = {}

        for rank, hit in enumerate(vector_hits):
            payload = getattr(hit, "payload", None) or {}
            chunk_id = self._chunk_id(hit)
            candidates.setdefault(
                chunk_id,
                {
                    "payload": payload,
                    "vector_rank": None,
                    "bm25_rank": None,
                    "vector_score": 0.0,
                    "bm25_score": 0.0,
                },
            )
            candidates[chunk_id]["payload"] = payload
            candidates[chunk_id]["vector_rank"] = rank
            candidates[chunk_id]["vector_score"] = float(getattr(hit, "score", 0.0) or 0.0)

        for rank, (hit, bm25_score) in enumerate(bm25_hits):
            payload = getattr(hit, "payload", None) or {}
            chunk_id = self._chunk_id(hit)
            candidates.setdefault(
                chunk_id,
                {
                    "payload": payload,
                    "vector_rank": None,
                    "bm25_rank": None,
                    "vector_score": 0.0,
                    "bm25_score": 0.0,
                },
            )
            candidates[chunk_id]["payload"] = payload
            candidates[chunk_id]["bm25_rank"] = rank
            candidates[chunk_id]["bm25_score"] = float(bm25_score)

        rrf_k = max(1, int(settings.qdrant_rrf_k))

        def _fusion_score(candidate: dict) -> float:
            score = 0.0
            vector_rank = candidate["vector_rank"]
            bm25_rank = candidate["bm25_rank"]
            if vector_rank is not None:
                score += 1.0 / (rrf_k + vector_rank + 1)
            if bm25_rank is not None:
                score += 1.0 / (rrf_k + bm25_rank + 1)
            return score

        ranked = sorted(candidates.items(), key=lambda item: _fusion_score(item[1]), reverse=True)

        items: list[RetrievedEvidence] = []
        for chunk_id, candidate in ranked:
            payload = candidate["payload"] or {}
            if not _is_payload_allowed(payload):
                continue
            text = str(payload.get("text", ""))
            if not text:
                continue
            items.append(
                RetrievedEvidence(
                    chunk_id=chunk_id,
                    score=_fusion_score(candidate),
                    text=text,
                    payload=payload,
                )
            )
            if len(items) >= top_k:
                break
        return items

    def search(
        self,
        query: str,
        top_k: int = 5,
        industry_tag: str | None = None,
        project_id: str | None = None,
    ) -> list[RetrievedEvidence]:
        embed_profile = resolve_profile_for_task(project_id=project_id, task_type="EMBED")
        query_filter = self._build_query_filter(industry_tag=industry_tag)

        query_vector = embed_text(
            query,
            self.vector_size,
            model_id=embed_profile.model,
            provider=embed_profile.provider,
            api_key=embed_profile.api_key,
            base_url=embed_profile.base_url,
            project_id=project_id,
        )
        vector_hits = self._vector_search(query_vector=query_vector, query_filter=query_filter, limit=max(top_k * 4, 8))

        bm25_hits = self._bm25_scores(
            query=query,
            query_filter=query_filter,
            limit=max(top_k * 8, int(settings.qdrant_hybrid_candidate_limit)),
        )

        if bm25_hits:
            return self._fuse_hybrid(vector_hits=vector_hits, bm25_hits=bm25_hits, top_k=top_k)

        items: list[RetrievedEvidence] = []
        for hit in vector_hits:
            payload = getattr(hit, "payload", None) or {}
            if not _is_payload_allowed(payload):
                continue
            items.append(
                RetrievedEvidence(
                    chunk_id=str(payload.get("chunk_id", getattr(hit, "id", ""))),
                    score=float(getattr(hit, "score", 0.0) or 0.0),
                    text=str(payload.get("text", "")),
                    payload=payload,
                )
            )
            if len(items) >= top_k:
                break
        return items


def to_search_hits(items: list[RetrievedEvidence]) -> list[EvidenceSearchHit]:
    return [EvidenceSearchHit(chunk_id=i.chunk_id, score=i.score, text=i.text, payload=i.payload) for i in items]
