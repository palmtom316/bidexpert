from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from math import log

from app.core.config import settings

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


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


def compress_evidence_context(requirement_text: str, evidence_texts: list[str]) -> CompressionResult:
    if not evidence_texts:
        return CompressionResult(evidence_texts=[], original_chars=0, compressed_chars=0, dropped_count=0)

    max_items = max(1, int(settings.context_compression_max_items))
    max_chars = max(200, int(settings.context_compression_max_chars))
    snippet_chars = max(80, int(settings.context_compression_snippet_chars))

    original_chars = sum(len(item) for item in evidence_texts)
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
        selected = fallback[:max_items]
        used_chars = sum(len(item) for item in selected)

    return CompressionResult(
        evidence_texts=selected,
        original_chars=original_chars,
        compressed_chars=used_chars,
        dropped_count=max(0, len(evidence_texts) - len(selected)),
    )

