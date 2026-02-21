from __future__ import annotations

import hashlib
import logging
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import cast

from app.core.config import settings
from app.schemas.contracts import EvidenceSearchHit, EvidenceUpsertItem
from app.services.byok import resolve_profile_for_task
from app.services.embedding import embed_text

logger = logging.getLogger(__name__)
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
NUMERIC_TOKEN_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:kV|KV|kv|V|A|kW|MW|Hz|MHz|GHz|mm|cm|m)")
MODEL_TOKEN_PATTERN = re.compile(r"\b[A-Za-z]{1,6}[-_ ]?\d{2,}[A-Za-z0-9-]*\b")

SPARSE_VECTOR_NAME = "bm25_sparse"


@dataclass
class RetrievedEvidence:
    chunk_id: str
    score: float
    text: str
    payload: dict


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall((text or "").lower())


def _build_sparse_vector(text: str) -> dict[int, float]:
    tokens = _tokenize(text)
    if not tokens:
        return {}
    tf = Counter(tokens)
    total = len(tokens)
    indices_values: dict[int, float] = {}
    for token, count in tf.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest, byteorder="big", signed=False) % (2**31)
        indices_values[idx] = count / total
    return indices_values


def _rerank_hits(query: str, items: list[RetrievedEvidence], top_k: int) -> list[RetrievedEvidence]:
    query_tokens = set(_tokenize(query))
    normalized_query = (query or "").strip().lower()
    if not query_tokens and not normalized_query:
        return items[:top_k]

    def _lexical_relevance(text: str) -> float:
        normalized_text = (text or "").strip().lower()
        if normalized_query and normalized_query in normalized_text:
            return 1.0

        text_tokens = set(_tokenize(text))
        if query_tokens:
            token_overlap = len(query_tokens & text_tokens) / len(query_tokens)
        else:
            token_overlap = 0.0

        query_chars = "".join(ch for ch in normalized_query if "\u4e00" <= ch <= "\u9fff")
        if len(query_chars) >= 2:
            bigram_hits = 0
            total = len(query_chars) - 1
            for idx in range(total):
                gram = query_chars[idx : idx + 2]
                if gram and gram in normalized_text:
                    bigram_hits += 1
            bigram_overlap = bigram_hits / total if total > 0 else 0.0
        else:
            bigram_overlap = 0.0
        return max(token_overlap, bigram_overlap)

    def _rerank_score(item: RetrievedEvidence) -> float:
        base_score = float(item.score)
        overlap = _lexical_relevance(item.text)
        quality = float(item.payload.get("quality_score", 0.0) or 0.0) / 100.0
        quality = max(0.0, min(1.0, quality))
        return base_score * 0.55 + overlap * 0.40 + quality * 0.05

    scored = [(item, _rerank_score(item)) for item in items]
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    result: list[RetrievedEvidence] = []
    for item, score in ranked[:top_k]:
        result.append(
            RetrievedEvidence(
                chunk_id=item.chunk_id,
                score=score,
                text=item.text,
                payload=item.payload,
            )
        )
    return result


def _extract_key_fact_tokens(query: str) -> set[str]:
    normalized_query = (query or "").strip()
    tokens: set[str] = set()
    for match in NUMERIC_TOKEN_PATTERN.findall(normalized_query):
        token = re.sub(r"\s+", "", match).lower()
        if token:
            tokens.add(token)
    for match in MODEL_TOKEN_PATTERN.findall(normalized_query):
        token = re.sub(r"\s+", "", match).lower()
        if token:
            tokens.add(token)
    return tokens


def _apply_key_fact_filter(query: str, items: list[RetrievedEvidence]) -> list[RetrievedEvidence]:
    key_tokens = _extract_key_fact_tokens(query)
    if not key_tokens:
        return items

    filtered: list[RetrievedEvidence] = []
    for item in items:
        target = re.sub(r"\s+", "", item.text.lower())
        payload_text = str(item.payload.get("parent_context", "") or "").lower()
        payload_target = re.sub(r"\s+", "", payload_text)
        if any(token in target or token in payload_target for token in key_tokens):
            filtered.append(item)
    return filtered or items


@lru_cache(maxsize=1)
def _load_cross_encoder(model_name: str):
    from sentence_transformers import CrossEncoder

    return CrossEncoder(model_name)


def _cross_encoder_rerank_hits(query: str, items: list[RetrievedEvidence], top_k: int) -> list[RetrievedEvidence]:
    if not items:
        return []
    if not bool(getattr(settings, "qdrant_cross_encoder_enabled", False)):
        return _rerank_hits(query=query, items=items, top_k=top_k)

    model_name = str(getattr(settings, "qdrant_cross_encoder_model", "")).strip()
    if not model_name:
        return _rerank_hits(query=query, items=items, top_k=top_k)

    try:
        model = _load_cross_encoder(model_name)
        pairs = [(query, item.text) for item in items]
        scores = model.predict(pairs)
    except Exception:
        logger.warning("cross-encoder rerank unavailable; fallback to lexical rerank")
        return _rerank_hits(query=query, items=items, top_k=top_k)

    scored = list(zip(items, [float(score) for score in scores], strict=False))
    ranked = sorted(scored, key=lambda pair: pair[1], reverse=True)
    result: list[RetrievedEvidence] = []
    for item, score in ranked[:top_k]:
        result.append(
            RetrievedEvidence(
                chunk_id=item.chunk_id,
                score=score,
                text=item.text,
                payload=item.payload,
            )
        )
    return result


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
        from qdrant_client.http.models import Distance, SparseVectorParams, VectorParams

        self.client = QdrantClient(url=settings.qdrant_url, check_compatibility=False)
        self.collection = settings.qdrant_collection
        self.vector_size = settings.qdrant_vector_size
        self._sparse_enabled = False

        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection for c in collections)
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
                sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
            )
            self._sparse_enabled = True
        else:
            try:
                info = self.client.get_collection(self.collection)
                sparse_cfg = getattr(info.config.params, "sparse_vectors", None) or {}
                self._sparse_enabled = SPARSE_VECTOR_NAME in sparse_cfg
            except Exception:
                self._sparse_enabled = False

        if not self._sparse_enabled:
            try:
                self.client.update_collection(
                    collection_name=self.collection,
                    sparse_vectors_config={SPARSE_VECTOR_NAME: SparseVectorParams()},
                )
                self._sparse_enabled = True
            except Exception:
                logger.info("Sparse vector upgrade unavailable; falling back to dense only")

    def upsert_chunks(self, expert_doc_id: str, chunks: list[EvidenceUpsertItem], project_id: str | None = None) -> int:
        from qdrant_client.http.models import PointStruct, SparseVector

        embed_profile = resolve_profile_for_task(project_id=project_id, task_type="EMBED")
        points: list[PointStruct] = []
        for chunk in chunks:
            source_locator = chunk.source_locator or {}
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
                "source_locator": source_locator,
                "text": chunk.text,
                "embed_provider": embed_profile.provider,
                "embed_model": embed_profile.model,
                "doc_id": source_locator.get("doc_id"),
                "section_id": source_locator.get("section_id"),
                "discipline": source_locator.get("discipline"),
                "source_page": source_locator.get("source_page"),
                "parent_chunk_id": chunk.parent_chunk_id or source_locator.get("parent_chunk_id"),
                "anchor_type": chunk.anchor_type or source_locator.get("anchor_type"),
                "parent_context": source_locator.get("parent_context"),
            }

            dense_vector = embed_text(
                chunk.text,
                self.vector_size,
                model_id=embed_profile.model,
                provider=embed_profile.provider,
                api_key=embed_profile.api_key,
                base_url=embed_profile.base_url,
                project_id=project_id,
            )

            point_kwargs: dict = {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{expert_doc_id}:{chunk.chunk_id}")),
                "vector": dense_vector,
                "payload": payload,
            }

            if self._sparse_enabled:
                sparse = _build_sparse_vector(chunk.text)
                if sparse:
                    point_kwargs["vector"] = {
                        "": dense_vector,
                        SPARSE_VECTOR_NAME: SparseVector(
                            indices=list(sparse.keys()),
                            values=list(sparse.values()),
                        ),
                    }

            points.append(PointStruct(**point_kwargs))

        if points:
            self.client.upsert(collection_name=self.collection, points=points, wait=True)
        return len(points)

    def _build_query_filter(self, industry_tag: str | None = None):
        from qdrant_client.http.models import Condition, FieldCondition, Filter, MatchValue

        must_conditions: list[Condition] = [FieldCondition(key="sensitivity_level", match=MatchValue(value="PUBLIC_OK"))]
        if industry_tag:
            must_conditions.append(FieldCondition(key="industry_tag", match=MatchValue(value=industry_tag)))
        must_not_conditions: list[Condition] = [FieldCondition(key="forbidden_tags", match=MatchValue(value="PRICING_RELATED"))]
        return Filter(must=cast(list[Condition], must_conditions), must_not=cast(list[Condition], must_not_conditions))

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
            self.client.search(  # type: ignore[attr-defined]
                collection_name=self.collection,
                query_vector=query_vector,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
        )

    def _sparse_search(self, sparse_vector: dict[int, float], query_filter, limit: int):
        from qdrant_client.http.models import NamedSparseVector, SparseVector

        if not sparse_vector:
            return []
        named_sparse = NamedSparseVector(
            name=SPARSE_VECTOR_NAME,
            vector=SparseVector(indices=list(sparse_vector.keys()), values=list(sparse_vector.values())),
        )
        return list(
            self.client.search(  # type: ignore[attr-defined]
                collection_name=self.collection,
                query_vector=named_sparse,
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        )

    def _chunk_id(self, point: object) -> str:
        payload = getattr(point, "payload", None) or {}
        return str(payload.get("chunk_id", getattr(point, "id", "")))

    def _fuse_hybrid(
        self,
        *,
        vector_hits: list[object],
        sparse_hits: list[object],
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
                    "sparse_rank": None,
                    "vector_score": 0.0,
                    "sparse_score": 0.0,
                },
            )
            candidates[chunk_id]["payload"] = payload
            candidates[chunk_id]["vector_rank"] = rank
            candidates[chunk_id]["vector_score"] = float(getattr(hit, "score", 0.0) or 0.0)

        for rank, hit in enumerate(sparse_hits):
            payload = getattr(hit, "payload", None) or {}
            chunk_id = self._chunk_id(hit)
            candidates.setdefault(
                chunk_id,
                {
                    "payload": payload,
                    "vector_rank": None,
                    "sparse_rank": None,
                    "vector_score": 0.0,
                    "sparse_score": 0.0,
                },
            )
            candidates[chunk_id]["payload"] = payload
            candidates[chunk_id]["sparse_rank"] = rank
            candidates[chunk_id]["sparse_score"] = float(getattr(hit, "score", 0.0) or 0.0)

        rrf_k = max(1, int(settings.qdrant_rrf_k))

        def _fusion_score(candidate: dict) -> float:
            score = 0.0
            vector_rank = candidate.get("vector_rank")
            sparse_rank = candidate.get("sparse_rank")
            if vector_rank is not None:
                score += 1.0 / (rrf_k + vector_rank + 1)
            if sparse_rank is not None:
                score += 1.0 / (rrf_k + sparse_rank + 1)
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
        prompt_top_n = max(
            int(settings.qdrant_prompt_topn_min),
            min(int(top_k), int(settings.qdrant_prompt_topn_max)),
        )
        candidate_limit = max(
            int(settings.qdrant_hybrid_topk_min),
            min(
                max(prompt_top_n * 5, int(settings.qdrant_hybrid_candidate_limit)),
                int(settings.qdrant_hybrid_topk_max),
            ),
        )

        dense_query = embed_text(
            query,
            self.vector_size,
            model_id=embed_profile.model,
            provider=embed_profile.provider,
            api_key=embed_profile.api_key,
            base_url=embed_profile.base_url,
            project_id=project_id,
        )
        vector_hits = self._vector_search(
            query_vector=dense_query,
            query_filter=query_filter,
            limit=max(candidate_limit, 8),
        )

        sparse_hits: list[object] = []
        if self._sparse_enabled:
            sparse_query = _build_sparse_vector(query)
            sparse_hits = self._sparse_search(
                sparse_vector=sparse_query,
                query_filter=query_filter,
                limit=max(candidate_limit, int(settings.qdrant_hybrid_candidate_limit)),
            )

        if vector_hits or sparse_hits:
            rerank_enabled = bool(getattr(settings, "qdrant_enable_rerank", False))
            if rerank_enabled:
                rerank_candidate_limit = max(candidate_limit, int(settings.qdrant_rerank_candidate_limit))
                fused = self._fuse_hybrid(
                    vector_hits=vector_hits,
                    sparse_hits=sparse_hits,
                    top_k=rerank_candidate_limit,
                )
                reranked = _cross_encoder_rerank_hits(query=query, items=fused, top_k=prompt_top_n)
                return _apply_key_fact_filter(query=query, items=reranked)[:prompt_top_n]
            fused = self._fuse_hybrid(vector_hits=vector_hits, sparse_hits=sparse_hits, top_k=prompt_top_n)
            return _apply_key_fact_filter(query=query, items=fused)[:prompt_top_n]

        return []


@lru_cache(maxsize=1)
def get_qdrant_store() -> QdrantStore:
    return QdrantStore()


def to_search_hits(items: list[RetrievedEvidence]) -> list[EvidenceSearchHit]:
    return [EvidenceSearchHit(chunk_id=i.chunk_id, score=i.score, text=i.text, payload=i.payload) for i in items]
