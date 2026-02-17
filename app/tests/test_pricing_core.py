from __future__ import annotations

import json

import pytest

from app.core import pricing
from app.core.config import settings


def test_pricing_uses_file_override(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(
        json.dumps(
            {
                "custom-model": {
                    "input_price_per_m": 1.0,
                    "output_price_per_m": 2.0,
                    "currency": "usd",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(settings, "pricing_file", str(pricing_file), raising=False)
    pricing.reset_pricing_cache()
    cost, currency = pricing.get_estimated_cost("custom-model", 1_000_000, 500_000)
    pricing.reset_pricing_cache()

    assert cost == pytest.approx(2.0)
    assert currency == "USD"


def test_pricing_match_uses_exact_or_prefix_not_contains(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "pricing_file", None, raising=False)
    pricing.reset_pricing_cache()

    cost_prefix, _ = pricing.get_estimated_cost("gpt-4o-mini:online", 1_000_000, 0)
    cost_contains, _ = pricing.get_estimated_cost("foo-gpt-4o", 1_000_000, 0)
    pricing.reset_pricing_cache()

    assert cost_prefix == pytest.approx(0.15)
    assert cost_contains == pytest.approx(0.15)
