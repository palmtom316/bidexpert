from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from time import sleep

import redis
from redis.exceptions import RedisError

from app.core.config import settings


@dataclass
class CacheRecord:
    payload: dict
    expires_at: datetime


_CACHE: dict[str, CacheRecord] = {}
_LOCK = threading.Lock()
_CACHE_PREFIX = "semantic_cache:"
_CLEANUP_STARTED = False


@lru_cache(maxsize=1)
def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _redis_key(cache_key: str) -> str:
    return f"{_CACHE_PREFIX}{cache_key}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def requirement_fingerprint(requirement_text: str) -> str:
    return _sha256_text(requirement_text.strip())


def evidence_fingerprint(evidence_ids: list[str]) -> str:
    normalized = json.dumps(sorted(evidence_ids), ensure_ascii=False)
    return _sha256_text(normalized)


def build_cache_key(
    industry_tag: str | None,
    tender_template_id: str | None,
    requirement_text: str,
    evidence_ids: list[str],
) -> str:
    return ":".join(
        [
            industry_tag or "_",
            tender_template_id or "_",
            requirement_fingerprint(requirement_text),
            evidence_fingerprint(evidence_ids),
            settings.schema_version,
        ]
    )


def _prune_local_cache_locked(now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    expired_keys = [key for key, record in _CACHE.items() if now >= record.expires_at]
    for key in expired_keys:
        _CACHE.pop(key, None)

    max_entries = max(1, int(settings.semantic_cache_max_local_entries))
    overflow = len(_CACHE) - max_entries
    if overflow > 0:
        evict_keys = sorted(_CACHE.items(), key=lambda item: item[1].expires_at)[:overflow]
        for key, _ in evict_keys:
            _CACHE.pop(key, None)


def _cleanup_loop() -> None:
    interval = max(1, int(settings.semantic_cache_cleanup_interval_seconds))
    while True:
        sleep(interval)
        with _LOCK:
            _prune_local_cache_locked()


def _ensure_local_cleanup_thread() -> None:
    global _CLEANUP_STARTED
    if _CLEANUP_STARTED:
        return
    with _LOCK:
        if _CLEANUP_STARTED:
            return
        worker = threading.Thread(target=_cleanup_loop, name="semantic-cache-cleaner", daemon=True)
        worker.start()
        _CLEANUP_STARTED = True


def _get_cache_local(cache_key: str) -> dict | None:
    _ensure_local_cleanup_thread()
    with _LOCK:
        _prune_local_cache_locked()
        record = _CACHE.get(cache_key)
        if not record:
            return None
        return dict(record.payload)


def get_cache(cache_key: str) -> dict | None:
    try:
        value = _redis_client().get(_redis_key(cache_key))
        if value is None:
            return _get_cache_local(cache_key)
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (RedisError, json.JSONDecodeError):
        return _get_cache_local(cache_key)


def _set_cache_local(cache_key: str, payload: dict, ttl_seconds: int) -> None:
    _ensure_local_cleanup_thread()
    with _LOCK:
        _prune_local_cache_locked()
        _CACHE[cache_key] = CacheRecord(
            payload=dict(payload),
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        )


def set_cache(cache_key: str, payload: dict, ttl_seconds: int = 3600) -> None:
    try:
        _redis_client().set(_redis_key(cache_key), json.dumps(payload, ensure_ascii=False), ex=ttl_seconds)
    except RedisError:
        _set_cache_local(cache_key, payload, ttl_seconds)


def invalidate_cache(prefix: str | None = None) -> int:
    count = 0
    pattern = f"{_CACHE_PREFIX}{prefix or ''}*"
    try:
        client = _redis_client()
        keys = list(client.scan_iter(match=pattern, count=500))
        if keys:
            count += int(client.delete(*keys))
    except RedisError:
        pass

    with _LOCK:
        if prefix is None:
            count += len(_CACHE)
            _CACHE.clear()
            return count
        keys = [k for k in _CACHE if k.startswith(prefix)]
        for key in keys:
            _CACHE.pop(key, None)
        return count + len(keys)
