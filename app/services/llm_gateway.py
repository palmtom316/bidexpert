from __future__ import annotations

from app.services.adapters import (
    AdapterUnavailableError,
    GenerationRequest,
    GenerationResult,
    QueryRewriteRequest,
    QueryRewriteResult,
    ReviewRequest,
    ReviewResult,
    create_adapter,
)

def _select_adapter(provider: str):
    return create_adapter(provider)


def generate_with_profile(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    requirement_text: str,
    evidence_texts: list[str],
    evidence_ids: list[str],
) -> GenerationResult:
    adapter = _select_adapter(provider)
    payload = GenerationRequest(
        model=model,
        requirement_text=requirement_text,
        evidence_texts=evidence_texts,
        evidence_ids=evidence_ids,
        api_key=api_key,
        base_url=base_url,
    )
    return adapter.generate(payload)


def review_with_profile(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    draft_text: str,
    evidence_texts: list[str],
) -> ReviewResult:
    adapter = _select_adapter(provider)
    payload = ReviewRequest(
        model=model,
        draft_text=draft_text,
        evidence_texts=evidence_texts,
        api_key=api_key,
        base_url=base_url,
    )
    return adapter.review(payload)


def rewrite_query_with_profile(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    query: str,
) -> QueryRewriteResult:
    adapter = _select_adapter(provider)
    payload = QueryRewriteRequest(
        model=model,
        query=query,
        api_key=api_key,
        base_url=base_url,
    )
    return adapter.rewrite_query(payload)


__all__ = [
    "AdapterUnavailableError",
    "generate_with_profile",
    "rewrite_query_with_profile",
    "review_with_profile",
]
