from __future__ import annotations

from collections.abc import Callable

from app.services.adapters.base import LLMAdapter
from app.services.adapters.providers import (
    DeepSeekAdapter,
    GeminiAdapter,
    MockAdapter,
    OpenAIAdapter,
    OpenAICompatibleAdapter,
    QwenAdapter,
)

AdapterFactory = Callable[[], LLMAdapter]

ADAPTER_REGISTRY: dict[str, AdapterFactory] = {
    "openai": OpenAIAdapter,
    "gemini": GeminiAdapter,
    "qwen": QwenAdapter,
    "deepseek": DeepSeekAdapter,
}

_OPENAI_COMPATIBLE_FALLBACK = {"doubao", "glm"}


def create_adapter(provider: str) -> LLMAdapter:
    normalized = (provider or "").strip().lower()
    factory = ADAPTER_REGISTRY.get(normalized)
    if factory:
        return factory()
    if normalized in _OPENAI_COMPATIBLE_FALLBACK:
        return OpenAICompatibleAdapter(provider=normalized)
    return MockAdapter()


def list_registered_providers() -> list[str]:
    return sorted(ADAPTER_REGISTRY.keys())

