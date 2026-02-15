from __future__ import annotations

import hashlib
import logging
import math
import re

import httpx

from app.core.config import settings
from app.services.concurrency_limiter import ConcurrencyLimitExceeded, acquire_concurrency_slot

logger = logging.getLogger(__name__)

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _extract_embedding(raw: dict) -> list[float]:
    data = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
            return [float(v) for v in first["embedding"]]
    embeddings = raw.get("embeddings") if isinstance(raw, dict) else None
    if isinstance(embeddings, list) and embeddings and isinstance(embeddings[0], list):
        return [float(v) for v in embeddings[0]]
    raise RuntimeError("embedding API returned invalid payload")


def _post_embeddings(
    *,
    url: str,
    body: dict,
    api_key: str,
) -> list[float]:
    timeout = httpx.Timeout(float(settings.llm_http_timeout_seconds))
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=body,
            )
            resp.raise_for_status()
            raw = resp.json()
    except httpx.TimeoutException as exc:
        raise RuntimeError("embedding API timeout") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"embedding API returned {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("embedding API unavailable") from exc
    return _extract_embedding(raw)


def _call_embedding_api(
    text: str,
    *,
    provider: str,
    model: str,
    api_key: str,
    base_url: str,
) -> list[float]:
    normalized_provider = (provider or "").strip().lower()
    if normalized_provider == "voyage":
        # Voyage Embedding API requires list input and does not share chat-completions semantics.
        return _post_embeddings(
            url=f"{base_url.rstrip('/')}/embeddings",
            body={"model": model, "input": [text], "input_type": "document"},
            api_key=api_key,
        )
    return _post_embeddings(
        url=f"{base_url.rstrip('/')}/embeddings",
        body={"model": model, "input": text},
        api_key=api_key,
    )


def _mock_embed(text: str, vector_size: int, model_id: str | None = None) -> list[float]:
    """Deterministic hash-based pseudo-embedding for testing only."""
    vec = [0.0] * vector_size
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vec

    salt = (model_id or "").strip().lower()
    for token in tokens:
        payload = f"{salt}:{token}" if salt else token
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()  # noqa: S324
        idx = int(digest[:8], 16) % vector_size
        sign = 1.0 if (int(digest[8:10], 16) % 2 == 0) else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]


def embed_text(
    text: str,
    vector_size: int = 3072,
    model_id: str | None = None,
    *,
    provider: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    project_id: str | None = None,
) -> list[float]:
    """Generate an embedding vector for *text*.

    When *api_key* and *base_url* are provided, calls a real embedding API.
    Otherwise falls back to a deterministic hash-based mock (suitable for tests).
    """
    if api_key and base_url:
        try:
            with acquire_concurrency_slot(project_id=project_id, task_type="EMBED"):
                vec = _call_embedding_api(
                    text,
                    provider=provider or "openai",
                    model=model_id or "text-embedding-3-large",
                    api_key=api_key,
                    base_url=base_url,
                )
            if len(vec) >= vector_size:
                return vec[:vector_size]
            return vec + [0.0] * (vector_size - len(vec))
        except (RuntimeError, ConcurrencyLimitExceeded):
            logger.warning(
                "Embedding API failed for provider=%s model=%s, falling back to mock",
                provider,
                model_id,
                exc_info=True,
            )

    return _mock_embed(text, vector_size, model_id)
