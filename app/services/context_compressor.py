from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass
from math import log

from app.core.config import settings
from app.services.adapters import AdapterUnavailableError
from app.services.byok import resolve_profile_chain_for_task
from app.services.llm_gateway import generate_with_fallback_chain

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)
logger = logging.getLogger(__name__)


@dataclass
class CompressionResult:
    evidence_texts: list[str]
    original_chars: int
    compressed_chars: int
    dropped_count: int

    @property
    def compressed(self) -> bool:
        return self.compressed_chars < self.original_chars or self.dropped_count > 0


def _tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text.lower())


def _compress_with_llm(
    *,
    requirement_text: str,
    evidence_texts: list[str],
    max_items: int,
    max_chars: int,
    snippet_chars: int,
) -> list[str]:
    if not requirement_text.strip() or not evidence_texts:
        return []

    profile_chain = resolve_profile_chain_for_task(project_id=None, task_type="GENERATE")
    if not profile_chain:
        return []

    evidence_ids = [f"e-{idx}" for idx in range(1, len(evidence_texts) + 1)]
    prompt = (
        "从给定证据中挑选最能支撑需求的片段。"
        f"最多保留{max_items}条，且总字符数不超过{max_chars}。"
        "严禁引用未提供的证据编号。"
        f"\n需求：{requirement_text}"
    )
    try:
        result, _ = generate_with_fallback_chain(
            profile_chain=profile_chain,
            project_id=None,
            requirement_text=prompt,
            evidence_texts=evidence_texts,
            evidence_ids=evidence_ids,
        )
    except AdapterUnavailableError:
        return []
    except Exception as exc:  # noqa: BLE001
        logger.warning("context compression llm failed: %s", exc)
        return []

    content_json = result.content_json if isinstance(result.content_json, dict) else {}
    blocks = content_json.get("content_blocks") if isinstance(content_json, dict) else []
    if not isinstance(blocks, list):
        return []

    evidence_map = dict(zip(evidence_ids, evidence_texts, strict=False))
    ordered_ids: list[str] = []
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        ids = block.get("evidence_ids")
        if not isinstance(ids, list):
            continue
        for raw in ids:
            eid = str(raw).strip()
            if not eid or eid in seen or eid not in evidence_map:
                continue
            ordered_ids.append(eid)
            seen.add(eid)

    selected: list[str] = []
    used_chars = 0
    for eid in ordered_ids:
        snippet = evidence_map[eid].strip()[:snippet_chars]
        if not snippet:
            continue
        projected = used_chars + len(snippet)
        if selected and projected > max_chars:
            continue
        selected.append(snippet)
        used_chars = projected
        if len(selected) >= max_items or used_chars >= max_chars:
            break

    return selected


def _compress_with_local(
    *,
    requirement_text: str,
    evidence_texts: list[str],
    max_items: int,
    max_chars: int,
    snippet_chars: int,
) -> list[str]:
    query_terms = _tokenize(requirement_text)
    query_df = Counter(query_terms)
    docs_tokens = [_tokenize(item) for item in evidence_texts]
    avg_len = max(1.0, sum(len(tokens) for tokens in docs_tokens) / max(len(docs_tokens), 1))
    k1 = 1.2
    b = 0.75

    scored: list[tuple[float, int]] = []
    for idx, tokens in enumerate(docs_tokens):
        if not tokens:
            scored.append((0.0, idx))
            continue
        tf = Counter(tokens)
        dl = len(tokens)
        score = 0.0
        for term in query_df:
            if term not in tf:
                continue
            df = sum(1 for doc in docs_tokens if term in doc)
            idf = log(1 + (len(docs_tokens) - df + 0.5) / (df + 0.5))
            freq = tf[term]
            denom = freq + k1 * (1 - b + b * dl / avg_len)
            score += idf * (freq * (k1 + 1)) / max(denom, 1e-6)
        scored.append((score, idx))

    ordered = [idx for _score, idx in sorted(scored, key=lambda item: item[0], reverse=True)]

    selected: list[str] = []
    used_chars = 0
    for idx in ordered:
        if len(selected) >= max_items:
            break
        snippet = evidence_texts[idx].strip()
        if not snippet:
            continue
        snippet = snippet[:snippet_chars]
        projected = used_chars + len(snippet)
        if selected and projected > max_chars:
            continue
        selected.append(snippet)
        used_chars = projected
        if used_chars >= max_chars:
            break

    if not selected:
        fallback = [item.strip()[:snippet_chars] for item in evidence_texts if item.strip()]
        return fallback[:max_items]
    return selected


def compress_evidence_context(requirement_text: str, evidence_texts: list[str]) -> CompressionResult:
    if not evidence_texts:
        return CompressionResult(evidence_texts=[], original_chars=0, compressed_chars=0, dropped_count=0)

    max_items = max(1, int(settings.context_compression_max_items))
    max_chars = max(200, int(settings.context_compression_max_chars))
    snippet_chars = max(80, int(settings.context_compression_snippet_chars))

    original_chars = sum(len(item) for item in evidence_texts)
    selected: list[str] = []
    if bool(getattr(settings, "context_compression_use_llm", False)):
        selected = _compress_with_llm(
            requirement_text=requirement_text,
            evidence_texts=evidence_texts,
            max_items=max_items,
            max_chars=max_chars,
            snippet_chars=snippet_chars,
        )

    if not selected:
        selected = _compress_with_local(
            requirement_text=requirement_text,
            evidence_texts=evidence_texts,
            max_items=max_items,
            max_chars=max_chars,
            snippet_chars=snippet_chars,
        )

    used_chars = sum(len(item) for item in selected)

    return CompressionResult(
        evidence_texts=selected,
        original_chars=original_chars,
        compressed_chars=used_chars,
        dropped_count=max(0, len(evidence_texts) - len(selected)),
    )
