from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import cast

import redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.services.byok import get_project_model_policy

DEFAULT_LIMITS = {
    "extract": 2,
    "generate": 3,
    "review": 2,
    "embed": 2,
    "query_rewrite": 2,
    "program_support": 1,
}

_LOCAL_COUNTS: dict[str, int] = {}
_LOCAL_LOCK = threading.Lock()


class ConcurrencyLimitExceeded(RuntimeError):
    """Raised when a task exceeds the configured concurrency cap."""


def _normalize_task(task_type: str) -> str:
    return (task_type or "").strip().lower() or "generate"


def _limit_for(project_id: str | None, task_type: str) -> int:
    task_key = _normalize_task(task_type)
    fallback = int(DEFAULT_LIMITS.get(task_key, 1))
    if not project_id:
        return max(1, fallback)
    try:
        policy = get_project_model_policy(project_id)
    except ValueError:
        return max(1, fallback)
    if not policy:
        return max(1, fallback)
    limits = policy.concurrency_limits or {}
    raw = limits.get(task_key)
    if raw is None:
        return max(1, fallback)
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return max(1, fallback)


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


@contextmanager
def _local_slot(slot_key: str, limit: int) -> Iterator[None]:
    with _LOCAL_LOCK:
        current = int(_LOCAL_COUNTS.get(slot_key, 0))
        if current >= limit:
            raise ConcurrencyLimitExceeded(f"concurrency limit exceeded for {slot_key}")
        _LOCAL_COUNTS[slot_key] = current + 1
    try:
        yield
    finally:
        with _LOCAL_LOCK:
            current = int(_LOCAL_COUNTS.get(slot_key, 1)) - 1
            if current <= 0:
                _LOCAL_COUNTS.pop(slot_key, None)
            else:
                _LOCAL_COUNTS[slot_key] = current


_ACQUIRE_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, ttl)
end
if current > limit then
    redis.call('DECR', key)
    return 0
end
return 1
"""

_RELEASE_LUA = """
local key = KEYS[1]
local val = redis.call('DECR', key)
if val <= 0 then
    redis.call('DEL', key)
end
return val
"""


@contextmanager
def acquire_concurrency_slot(
    *,
    project_id: str | None,
    task_type: str,
    ttl_seconds: int = 180,
) -> Iterator[None]:
    task_key = _normalize_task(task_type)
    limit = _limit_for(project_id, task_key)
    slot_key = f"{project_id or '_'}:{task_key}"
    redis_key = f"concurrency:{slot_key}"
    try:
        client = _redis_client()
        result = client.eval(_ACQUIRE_LUA, 1, redis_key, str(limit), str(ttl_seconds))
        acquired = bool(int(cast(int, result)))
        if not acquired:
            raise ConcurrencyLimitExceeded(f"concurrency limit exceeded for {slot_key}")
        try:
            yield
        finally:
            try:
                client.eval(_RELEASE_LUA, 1, redis_key)
            except RedisError:
                pass
        return
    except RedisError:
        pass

    with _local_slot(slot_key, limit):
        yield

