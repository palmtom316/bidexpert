from __future__ import annotations

import threading
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class BudgetState:
    total: int
    used: int


_BUDGETS: dict[str, BudgetState] = {}
_LOCK = threading.Lock()


def estimate_tokens(text: str) -> int:
    # Approximation for budgeting and limiter checks.
    return max(1, len(text) // 4)


def get_budget(project_id: str | None) -> BudgetState:
    if not project_id:
        return BudgetState(total=settings.project_token_budget_default, used=0)

    with _LOCK:
        if project_id not in _BUDGETS:
            _BUDGETS[project_id] = BudgetState(total=settings.project_token_budget_default, used=0)
        state = _BUDGETS[project_id]
        return BudgetState(total=state.total, used=state.used)


def remaining_budget(project_id: str | None) -> int:
    state = get_budget(project_id)
    return max(0, state.total - state.used)


def reserve_budget(project_id: str | None, estimated_tokens: int) -> tuple[bool, int]:
    if not project_id:
        remaining = settings.project_token_budget_default
        return (estimated_tokens <= remaining, remaining - min(estimated_tokens, remaining))

    with _LOCK:
        state = _BUDGETS.setdefault(project_id, BudgetState(total=settings.project_token_budget_default, used=0))
        remaining = state.total - state.used
        if estimated_tokens > remaining:
            return (False, remaining)
        state.used += estimated_tokens
        return (True, state.total - state.used)


def reset_budget(project_id: str | None = None) -> int:
    with _LOCK:
        if project_id is None:
            count = len(_BUDGETS)
            _BUDGETS.clear()
            return count
        existed = int(project_id in _BUDGETS)
        _BUDGETS.pop(project_id, None)
        return existed
