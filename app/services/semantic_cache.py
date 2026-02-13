from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.config import settings


@dataclass
class CacheRecord:
    payload: dict
    expires_at: datetime


_CACHE: dict[str, CacheRecord] = {}
_LOCK = threading.Lock()


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


def get_cache(cache_key: str) -> dict | None:
    with _LOCK:
        record = _CACHE.get(cache_key)
        if not record:
            return None
        if datetime.utcnow() >= record.expires_at:
            _CACHE.pop(cache_key, None)
            return None
        return record.payload


def set_cache(cache_key: str, payload: dict, ttl_seconds: int = 3600) -> None:
    with _LOCK:
        _CACHE[cache_key] = CacheRecord(payload=payload, expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds))


def invalidate_cache(prefix: str | None = None) -> int:
    with _LOCK:
        if prefix is None:
            count = len(_CACHE)
            _CACHE.clear()
            return count
        keys = [k for k in _CACHE if k.startswith(prefix)]
        for key in keys:
            _CACHE.pop(key, None)
        return len(keys)
