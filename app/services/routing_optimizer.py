from __future__ import annotations

import json
import random
from threading import Lock
from typing import TYPE_CHECKING

import redis

from app.core.config import settings

if TYPE_CHECKING:
    from app.services.byok.profiles import ResolvedProfile


_MEMORY_STATS: dict[str, dict[str, dict[str, float]]] = {}
_LOCK = Lock()


def _bucket_name(project_id: str | None, task_type: str) -> str:
    return f"{(project_id or 'global').strip()}:{task_type.strip().upper()}"


def _profile_key(profile: ResolvedProfile) -> str:
    return f"{profile.provider.strip().lower()}::{profile.model.strip()}"


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _load_memory(bucket: str) -> dict[str, dict[str, float]]:
    with _LOCK:
        data = _MEMORY_STATS.get(bucket, {})
        return {
            key: {
                "attempts": float(item.get("attempts", 0.0)),
                "successes": float(item.get("successes", 0.0)),
                "latency_ms": float(item.get("latency_ms", 0.0)),
            }
            for key, item in data.items()
            if isinstance(item, dict)
        }


def _save_memory(bucket: str, payload: dict[str, dict[str, float]]) -> None:
    with _LOCK:
        _MEMORY_STATS[bucket] = payload


def _load_stats(bucket: str) -> dict[str, dict[str, float]]:
    key = f"rl-routing:{bucket}"
    try:
        raw = _redis_client().get(key)
        if not raw:
            return _load_memory(bucket)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return _load_memory(bucket)
        normalized: dict[str, dict[str, float]] = {}
        for item_key, item_val in parsed.items():
            if not isinstance(item_key, str) or not isinstance(item_val, dict):
                continue
            normalized[item_key] = {
                "attempts": float(item_val.get("attempts", 0.0)),
                "successes": float(item_val.get("successes", 0.0)),
                "latency_ms": float(item_val.get("latency_ms", 0.0)),
            }
        return normalized or _load_memory(bucket)
    except Exception:  # noqa: BLE001
        return _load_memory(bucket)


def _save_stats(bucket: str, payload: dict[str, dict[str, float]]) -> None:
    key = f"rl-routing:{bucket}"
    _save_memory(bucket, payload)
    try:
        _redis_client().set(key, json.dumps(payload, ensure_ascii=False), ex=7 * 24 * 3600)
    except Exception:  # noqa: BLE001
        return None


def _reward(item: dict[str, float] | None) -> float:
    if not item:
        return 0.5
    attempts = max(0.0, float(item.get("attempts", 0.0)))
    if attempts <= 0:
        return 0.5
    successes = max(0.0, float(item.get("successes", 0.0)))
    latency_ms = max(0.0, float(item.get("latency_ms", 0.0)))
    success_rate = min(1.0, successes / attempts)
    latency_bonus = 1.0 - min(1.0, latency_ms / 4000.0)
    return success_rate * 0.85 + latency_bonus * 0.15


def build_routing_order(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    task_type: str,
) -> list[int]:
    if len(profile_chain) <= 1 or not settings.rl_routing_enabled:
        return list(range(len(profile_chain)))

    bucket = _bucket_name(project_id, task_type)
    stats = _load_stats(bucket)
    indices = list(range(len(profile_chain)))

    explore_rate = float(settings.rl_routing_exploration_rate or 0.0)
    if explore_rate > 0 and random.random() < min(1.0, max(0.0, explore_rate)):
        random.shuffle(indices)
        return indices

    def _sort_key(idx: int) -> tuple[float, float, int]:
        key = _profile_key(profile_chain[idx])
        item = stats.get(key)
        attempts = float(item.get("attempts", 0.0)) if item else 0.0
        return (_reward(item), attempts, -idx)

    return sorted(indices, key=_sort_key, reverse=True)


def record_route_feedback(
    *,
    project_id: str | None,
    task_type: str,
    profile: ResolvedProfile,
    success: bool,
    latency_ms: int,
) -> None:
    if not settings.rl_routing_enabled:
        return

    bucket = _bucket_name(project_id, task_type)
    stats = _load_stats(bucket)
    key = _profile_key(profile)
    item = stats.get(key, {"attempts": 0.0, "successes": 0.0, "latency_ms": 0.0})

    attempts = float(item.get("attempts", 0.0)) + 1.0
    successes = float(item.get("successes", 0.0)) + (1.0 if success else 0.0)
    prev_latency = float(item.get("latency_ms", 0.0))
    new_latency = max(0.0, float(latency_ms))
    if attempts <= 1:
        avg_latency = new_latency
    else:
        avg_latency = prev_latency * 0.7 + new_latency * 0.3

    stats[key] = {
        "attempts": attempts,
        "successes": successes,
        "latency_ms": avg_latency,
    }
    _save_stats(bucket, stats)


__all__ = ["build_routing_order", "record_route_feedback"]
