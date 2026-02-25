"""Tests for app.services.routing_optimizer — RL routing logic."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.services.routing_optimizer import (
    _bucket_name,
    _profile_key,
    _reward,
    build_routing_order,
)


def _make_profile(provider: str, model: str) -> SimpleNamespace:
    return SimpleNamespace(provider=provider, model=model, api_key="k", base_url="u")


class TestBucketName:
    def test_with_project(self):
        assert _bucket_name("proj-1", "generate") == "proj-1:GENERATE"

    def test_none_project(self):
        assert _bucket_name(None, "review") == "global:REVIEW"

    def test_strips(self):
        assert _bucket_name("  proj  ", "  embed  ") == "proj:EMBED"


class TestProfileKey:
    def test_format(self):
        p = _make_profile("OpenAI", "gpt-4o")
        assert _profile_key(p) == "openai::gpt-4o"

    def test_strips(self):
        p = _make_profile("  Qwen  ", "  qwen-turbo  ")
        assert _profile_key(p) == "qwen::qwen-turbo"


class TestReward:
    def test_none_item(self):
        assert _reward(None) == 0.5

    def test_zero_attempts(self):
        assert _reward({"attempts": 0, "successes": 0, "latency_ms": 0}) == 0.5

    def test_perfect_fast(self):
        r = _reward({"attempts": 10, "successes": 10, "latency_ms": 0})
        assert r == pytest.approx(1.0)

    def test_perfect_slow(self):
        r = _reward({"attempts": 10, "successes": 10, "latency_ms": 4000})
        # success_rate=1.0*0.85 + latency_bonus=0*0.15 = 0.85
        assert r == pytest.approx(0.85)

    def test_zero_success(self):
        r = _reward({"attempts": 10, "successes": 0, "latency_ms": 0})
        # 0*0.85 + 1.0*0.15 = 0.15
        assert r == pytest.approx(0.15)


import pytest


class TestBuildRoutingOrder:
    def test_single_profile_returns_identity(self):
        profiles = [_make_profile("openai", "gpt-4o")]
        order = build_routing_order(profile_chain=profiles, project_id=None, task_type="generate")
        assert order == [0]

    def test_empty_returns_empty(self):
        order = build_routing_order(profile_chain=[], project_id=None, task_type="generate")
        assert order == []

    @patch("app.services.routing_optimizer.settings")
    def test_disabled_returns_natural_order(self, mock_settings):
        mock_settings.rl_routing_enabled = False
        profiles = [_make_profile("a", "m1"), _make_profile("b", "m2")]
        order = build_routing_order(profile_chain=profiles, project_id=None, task_type="generate")
        assert order == [0, 1]

    @patch("app.services.routing_optimizer._load_stats")
    @patch("app.services.routing_optimizer.settings")
    def test_sorts_by_reward(self, mock_settings, mock_load):
        mock_settings.rl_routing_enabled = True
        mock_settings.rl_routing_exploration_rate = 0.0
        mock_load.return_value = {
            "a::m1": {"attempts": 10, "successes": 5, "latency_ms": 2000},
            "b::m2": {"attempts": 10, "successes": 10, "latency_ms": 100},
        }
        profiles = [_make_profile("a", "m1"), _make_profile("b", "m2")]
        order = build_routing_order(profile_chain=profiles, project_id="p1", task_type="generate")
        # b::m2 has higher reward, so index 1 should come first
        assert order[0] == 1
