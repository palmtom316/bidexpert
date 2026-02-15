from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

import redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass
class BudgetState:
    total: int
    used: int


_BUDGETS: dict[str, BudgetState] = {}
_LOCK = threading.Lock()
_BUDGET_PREFIX = "budget:"


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _budget_key(project_id: str) -> str:
    return f"{_BUDGET_PREFIX}{project_id}"


def estimate_tokens(text: str) -> int:
    # Approximation for budgeting and limiter checks.
    return max(1, len(text) // 4)


def _get_budget_local(project_id: str | None) -> BudgetState:
    if not project_id:
        return BudgetState(total=settings.project_token_budget_default, used=0)

    with _LOCK:
        if project_id not in _BUDGETS:
            _BUDGETS[project_id] = BudgetState(total=settings.project_token_budget_default, used=0)
        state = _BUDGETS[project_id]
        return BudgetState(total=state.total, used=state.used)


def get_budget(project_id: str | None) -> BudgetState:
    if not project_id:
        return BudgetState(total=settings.project_token_budget_default, used=0)
    try:
        client = _redis_client()
        key = _budget_key(project_id)
        raw = client.hgetall(key)
        if not raw:
            client.hset(
                key,
                mapping={
                    "total": settings.project_token_budget_default,
                    "used": 0,
                },
            )
            return BudgetState(total=settings.project_token_budget_default, used=0)
        total = int(raw.get("total") or settings.project_token_budget_default)
        used = int(raw.get("used") or 0)
        return BudgetState(total=total, used=used)
    except (RedisError, TypeError, ValueError):
        return _get_budget_local(project_id)


def remaining_budget(project_id: str | None) -> int:
    state = get_budget(project_id)
    return max(0, state.total - state.used)


def reserve_budget(project_id: str | None, estimated_tokens: int) -> tuple[bool, int]:
    if not project_id:
        remaining = settings.project_token_budget_default
        return (estimated_tokens <= remaining, remaining - min(estimated_tokens, remaining))

    try:
        client = _redis_client()
        key = _budget_key(project_id)
        with client.pipeline() as pipe:
            while True:
                try:
                    pipe.watch(key)
                    raw = pipe.hgetall(key)
                    total = int((raw or {}).get("total") or settings.project_token_budget_default)
                    used = int((raw or {}).get("used") or 0)
                    remaining = max(0, total - used)
                    if estimated_tokens > remaining:
                        pipe.unwatch()
                        return (False, remaining)
                    new_used = used + estimated_tokens
                    pipe.multi()
                    pipe.hset(key, mapping={"total": total, "used": new_used})
                    pipe.execute()
                    return (True, max(0, total - new_used))
                except redis.WatchError:
                    continue
    except (RedisError, TypeError, ValueError):
        pass

    with _LOCK:
        state = _BUDGETS.setdefault(project_id, BudgetState(total=settings.project_token_budget_default, used=0))
        remaining = state.total - state.used
        if estimated_tokens > remaining:
            return (False, remaining)
        state.used += estimated_tokens
        return (True, state.total - state.used)


def reset_budget(project_id: str | None = None) -> int:
    removed = 0
    try:
        client = _redis_client()
        if project_id is None:
            keys = list(client.scan_iter(match=f"{_BUDGET_PREFIX}*", count=500))
            if keys:
                removed += int(client.delete(*keys))
        else:
            removed += int(client.delete(_budget_key(project_id)))
    except RedisError:
        pass

    with _LOCK:
        if project_id is None:
            count = len(_BUDGETS)
            _BUDGETS.clear()
            return removed + count
        existed = int(project_id in _BUDGETS)
        _BUDGETS.pop(project_id, None)
        return removed + existed
