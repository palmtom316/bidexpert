from __future__ import annotations

import threading
import time
from functools import lru_cache

import redis
from redis.exceptions import RedisError

from app.core.config import settings

_LOCAL_WINDOW_COUNTS: dict[str, tuple[int, int]] = {}
_LOCAL_LOCK = threading.Lock()

_ACQUIRE_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
if current > limit then
    return {0, redis.call('TTL', key)}
end
return {1, redis.call('TTL', key)}
"""


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def reset_local_rate_limit_state() -> None:
    with _LOCAL_LOCK:
        _LOCAL_WINDOW_COUNTS.clear()


def _local_allow_request(identifier: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = int(time.time())
    bucket = now // window_seconds
    with _LOCAL_LOCK:
        current_bucket, current_count = _LOCAL_WINDOW_COUNTS.get(identifier, (bucket, 0))
        if current_bucket != bucket:
            current_bucket, current_count = bucket, 0

        if current_count >= limit:
            retry_after = ((bucket + 1) * window_seconds) - now
            return False, max(1, retry_after)

        _LOCAL_WINDOW_COUNTS[identifier] = (current_bucket, current_count + 1)
        return True, 0


def _redis_allow_request(identifier: str, *, limit: int, window_seconds: int) -> tuple[bool, int]:
    key = f"api_rate:{identifier}"
    result = _redis_client().eval(_ACQUIRE_LUA, 1, key, str(limit), str(window_seconds))

    allowed = False
    retry_after = 0
    if isinstance(result, (list, tuple)) and len(result) >= 2:
        allowed = bool(int(result[0]))
        retry_after = int(result[1])
    elif result is not None:
        allowed = bool(int(result))

    if allowed:
        return True, 0
    return False, max(1, retry_after if retry_after > 0 else window_seconds)


def allow_api_request(
    *,
    identifier: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    safe_identifier = (identifier or "_").strip() or "_"
    safe_limit = max(1, int(limit))
    safe_window = max(1, int(window_seconds))

    try:
        return _redis_allow_request(safe_identifier, limit=safe_limit, window_seconds=safe_window)
    except RedisError:
        return _local_allow_request(safe_identifier, limit=safe_limit, window_seconds=safe_window)
