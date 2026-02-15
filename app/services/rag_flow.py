from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.adapters import AdapterUnavailableError
from app.services.byok import resolve_profile_for_task
from app.services.llm_gateway import rewrite_query_with_profile
from app.services.qdrant_store import QdrantStore, RetrievedEvidence


@dataclass
class SubRequirement:
    sub_id: str
    description: str
    category: str


@dataclass
class RetrievalLogItem:
    sub_id: str
    original_query: str
    rewritten_query: str
    provider: str
    model: str
    hit_ids: list[str]
    warning: str | None = None


def decompose_requirement(requirement_text: str) -> list[SubRequirement]:
    parts = [p.strip() for p in re.split(r"[，,；;。]+", requirement_text) if p.strip()]
    if not parts:
        return [SubRequirement(sub_id="sub-1", description=requirement_text, category="GENERAL")]

    result: list[SubRequirement] = []
    for idx, part in enumerate(parts, start=1):
        category = "MUST" if "必须" in part or "须" in part else "GENERAL"
        result.append(SubRequirement(sub_id=f"sub-{idx}", description=part, category=category))
    return result


def retrieve_for_subrequirements(
    sub_requirements: list[SubRequirement],
    top_k: int,
    industry_tag: str | None,
    project_id: str | None = None,
) -> tuple[dict[str, list[RetrievedEvidence]], list[dict]]:
    store = QdrantStore()
    retrieval: dict[str, list[RetrievedEvidence]] = {}
    retrieval_log: list[dict] = []
    for sub in sub_requirements:
        resolved = resolve_profile_for_task(project_id=project_id, task_type="QUERY_REWRITE")
        rewritten_query = sub.description
        warning: str | None = None
        try:
            rewritten = rewrite_query_with_profile(
                provider=resolved.provider,
                model=resolved.model,
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                query=sub.description,
            )
            rewritten_query = rewritten.rewritten_query.strip() or sub.description
        except AdapterUnavailableError:
            warning = "query_rewrite_fallback_original"
        hits = store.search(query=rewritten_query, top_k=top_k, industry_tag=industry_tag, project_id=project_id)
        retrieval[sub.sub_id] = hits
        retrieval_log.append(
            RetrievalLogItem(
                sub_id=sub.sub_id,
                original_query=sub.description,
                rewritten_query=rewritten_query,
                provider=resolved.provider,
                model=resolved.model,
                hit_ids=[hit.chunk_id for hit in hits],
                warning=warning,
            ).__dict__
        )
    return retrieval, retrieval_log


def merge_retrieval(retrieval: dict[str, list[RetrievedEvidence]]) -> tuple[list[str], dict[str, list[str]], list[RetrievedEvidence]]:
    merged: dict[str, RetrievedEvidence] = {}
    coverage_map: dict[str, list[str]] = {}

    for sub_id, hits in retrieval.items():
        coverage_map[sub_id] = []
        for hit in hits:
            merged[hit.chunk_id] = hit
            coverage_map[sub_id].append(hit.chunk_id)

    merged_hits = list(merged.values())
    merged_ids = list(merged.keys())
    return merged_ids, coverage_map, merged_hits
