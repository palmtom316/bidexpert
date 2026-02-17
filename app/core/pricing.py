from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    input_price_per_m: float
    output_price_per_m: float
    currency: str = "USD"


DEFAULT_PRICING_MAP: dict[str, ModelPricing] = {
    "gpt-4o": ModelPricing(5.00, 15.00),
    "gpt-4o-mini": ModelPricing(0.15, 0.60),
    "o1-preview": ModelPricing(15.00, 60.00),
    "o1-mini": ModelPricing(3.00, 12.00),
    "deepseek-chat": ModelPricing(0.28, 1.12),
    "deepseek-reasoner": ModelPricing(0.28, 1.12),
    "qwen-turbo": ModelPricing(0.28, 0.28),
    "qwen-plus": ModelPricing(0.56, 1.68),
    "qwen-max": ModelPricing(2.80, 8.40),
    "qwen3": ModelPricing(0.56, 1.68),
    "claude-3-5-sonnet-20241022": ModelPricing(3.00, 15.00),
    "claude-3-5-haiku-20241022": ModelPricing(1.00, 5.00),
}


def _coerce_pricing(model_name: str, payload: object) -> ModelPricing:
    if not isinstance(payload, dict):
        raise ValueError(f"invalid pricing entry type for model={model_name}")
    input_price = float(payload["input_price_per_m"])
    output_price = float(payload["output_price_per_m"])
    currency = str(payload.get("currency", "USD")).strip().upper() or "USD"
    return ModelPricing(
        input_price_per_m=input_price,
        output_price_per_m=output_price,
        currency=currency,
    )


def _load_pricing_from_file(path_str: str) -> dict[str, ModelPricing]:
    path = Path(path_str).expanduser()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("pricing file must be a JSON object")

    pricing_map: dict[str, ModelPricing] = {}
    for model, entry in raw.items():
        key = str(model).strip().lower()
        if not key:
            continue
        try:
            pricing_map[key] = _coerce_pricing(key, entry)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Skip invalid pricing entry for model=%s: %s", key, exc)
    if not pricing_map:
        raise ValueError("pricing file has no valid entries")
    return pricing_map


@lru_cache(maxsize=1)
def get_pricing_map() -> dict[str, ModelPricing]:
    pricing_file = (settings.pricing_file or "").strip()
    if pricing_file:
        try:
            return _load_pricing_from_file(pricing_file)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load BIDEXPERT_PRICING_FILE=%s: %s", pricing_file, exc)
    return DEFAULT_PRICING_MAP


def reset_pricing_cache() -> None:
    get_pricing_map.cache_clear()


def _resolve_pricing_key(model_name: str, pricing_map: dict[str, ModelPricing]) -> str | None:
    normalized = str(model_name or "").strip().lower()
    if not normalized:
        return None

    if normalized in pricing_map:
        return normalized

    alias = normalized.split("/")[-1]
    if alias in pricing_map:
        return alias

    separators = ("-", ":", "@", "/")
    candidates: list[str] = []

    def _collect_prefix_matches(source: str) -> None:
        for key in pricing_map:
            if any(source.startswith(f"{key}{sep}") for sep in separators):
                candidates.append(key)

    _collect_prefix_matches(normalized)
    if alias and alias != normalized:
        _collect_prefix_matches(alias)

    if not candidates:
        return None
    return max(candidates, key=len)


def get_estimated_cost(model_name: str, input_tokens: int, output_tokens: int) -> tuple[float, str]:
    pricing_map = get_pricing_map()
    key = _resolve_pricing_key(model_name, pricing_map)
    pricing = pricing_map[key] if key else pricing_map.get("gpt-4o-mini") or next(iter(pricing_map.values()))

    cost = (
        (input_tokens / 1_000_000 * pricing.input_price_per_m)
        + (output_tokens / 1_000_000 * pricing.output_price_per_m)
    )
    return cost, pricing.currency
