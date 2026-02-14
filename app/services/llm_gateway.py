from __future__ import annotations

from app.services.adapters import (
    AdapterUnavailableError,
    GenerationRequest,
    GenerationResult,
    MockAdapter,
    OpenAICompatibleAdapter,
    ReviewRequest,
    ReviewResult,
)

_OPENAI_COMPATIBLE = {"openai", "qwen", "deepseek", "doubao", "gemini", "glm"}


def _select_adapter(provider: str):
    normalized = (provider or "").strip().lower()
    if normalized in _OPENAI_COMPATIBLE:
        return OpenAICompatibleAdapter(provider=normalized)
    return MockAdapter()


def generate_with_profile(
    *,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    requirement_text: str,
    evidence_texts: list[str],
) -> GenerationResult:
    adapter = _select_adapter(provider)
    payload = GenerationRequest(
        model=model,
        requirement_text=requirement_text,
        evidence_texts=evidence_texts,
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


__all__ = [
    "AdapterUnavailableError",
    "generate_with_profile",
    "review_with_profile",
]
