from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.adapters import AdapterUnavailableError
from app.services.byok import resolve_profile_for_task
from app.services.llm_gateway import rewrite_query_with_profile
from app.services.qdrant_store import RetrievedEvidence, get_qdrant_store

_POWER_BOOST_TERMS = {
    "变电站", "输电线路", "配电网", "GIS", "变压器",
    "继电保护", "带电作业", "调试", "架线", "铁塔",
    "接地", "电缆", "开关柜", "互感器", "避雷器",
}


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


def _classify_sub_requirement(text: str) -> str:
    if re.search(r"资质|资格|许可证|承装修试|等级", text):
        return "QUALIFICATION"
    if re.search(r"业绩|案例|类似工程|合同", text):
        return "PERFORMANCE"
    if re.search(r"参数|容量|电压|截面|型号|规格|kV|MVA|MW", text):
        return "TECH_PARAM"
    if re.search(r"人员|项目经理|建造师|工程师|持证", text):
        return "PERSONNEL"
    if re.search(r"必须|应当|不得|须|严禁", text):
        return "MUST"
    return "GENERAL"


_CONTINUATION_WORDS = {"且", "并", "及", "以及", "同时", "另外"}


def decompose_requirement(requirement_text: str) -> list[SubRequirement]:
    raw_parts = [p.strip() for p in re.split(r"[，,；;。]+", requirement_text) if p.strip()]
    if not raw_parts:
        return [SubRequirement(sub_id="sub-1", description=requirement_text, category="GENERAL")]

    # Merge short fragments and those starting with continuation words
    merged: list[str] = []
    for part in raw_parts:
        if merged and (len(part) < 8 or any(part.startswith(w) for w in _CONTINUATION_WORDS)):
            merged[-1] = merged[-1] + "，" + part
        else:
            merged.append(part)

    result: list[SubRequirement] = []
    for idx, part in enumerate(merged, start=1):
        category = _classify_sub_requirement(part)
        result.append(SubRequirement(sub_id=f"sub-{idx}", description=part, category=category))
    return result


def retrieve_for_subrequirements(
    sub_requirements: list[SubRequirement],
    top_k: int,
    industry_tag: str | None,
    project_id: str | None = None,
) -> tuple[dict[str, list[RetrievedEvidence]], list[dict]]:
    store = get_qdrant_store()
    retrieval: dict[str, list[RetrievedEvidence]] = {}
    retrieval_log: list[dict] = []
    for sub in sub_requirements:
        resolved = resolve_profile_for_task(project_id=project_id, task_type="QUERY_REWRITE")
        rewritten_query = sub.description
        warning: str | None = None
        try:
            rewritten = rewrite_query_with_profile(
                project_id=project_id,
                provider=resolved.provider,
                model=resolved.model,
                api_key=resolved.api_key,
                base_url=resolved.base_url,
                query=sub.description,
            )
            rewritten_query = rewritten.rewritten_query.strip() or sub.description
        except AdapterUnavailableError:
            warning = "query_rewrite_fallback_original"
        methodology_hits = store.search_methodology(query=rewritten_query, top_k=top_k, domain=industry_tag)
        converted_methodology_hits: list[RetrievedEvidence] = [
            RetrievedEvidence(
                chunk_id=hit.snippet_id,
                score=hit.score,
                text=hit.text,
                payload={**hit.payload, "kb_source": "kb_methodology"},
            )
            for hit in methodology_hits
        ]

        history_hits = store.search(query=rewritten_query, top_k=top_k, industry_tag=industry_tag, project_id=project_id)
        merged_hits: list[RetrievedEvidence] = []
        seen_ids: set[str] = set()
        for item in [*converted_methodology_hits, *history_hits]:
            if item.chunk_id in seen_ids:
                continue
            seen_ids.add(item.chunk_id)
            merged_hits.append(item)
            if len(merged_hits) >= top_k:
                break

        retrieval[sub.sub_id] = merged_hits
        retrieval_log.append(
            RetrievalLogItem(
                sub_id=sub.sub_id,
                original_query=sub.description,
                rewritten_query=rewritten_query,
                provider=resolved.provider,
                model=resolved.model,
                hit_ids=[hit.chunk_id for hit in merged_hits],
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
