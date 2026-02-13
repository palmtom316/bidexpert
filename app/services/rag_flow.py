from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.qdrant_store import QdrantStore, RetrievedEvidence


@dataclass
class SubRequirement:
    sub_id: str
    description: str
    category: str


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
) -> dict[str, list[RetrievedEvidence]]:
    store = QdrantStore()
    retrieval: dict[str, list[RetrievedEvidence]] = {}
    for sub in sub_requirements:
        retrieval[sub.sub_id] = store.search(query=sub.description, top_k=top_k, industry_tag=industry_tag)
    return retrieval


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
