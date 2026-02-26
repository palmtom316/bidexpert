from __future__ import annotations

import hashlib
import re

_FROZEN_BLOCK_PATTERN = re.compile(r"\[FROZEN:(?P<key>[^\]]+)\](?P<body>.*?)\[/FROZEN\]", re.DOTALL)


def build_frozen_block_signatures(text: str) -> dict[str, str]:
    signatures: dict[str, str] = {}
    for match in _FROZEN_BLOCK_PATTERN.finditer(text or ""):
        key = match.group("key").strip()
        body = match.group("body")
        if not key:
            continue
        if key in signatures:
            raise ValueError(f"duplicate frozen block key: {key}")
        signatures[key] = hashlib.md5(body.encode("utf-8"), usedforsecurity=False).hexdigest()
    return signatures


def verify_frozen_block_signatures(text: str, expected_signatures: dict[str, str]) -> None:
    actual = build_frozen_block_signatures(text)
    for key, expected in expected_signatures.items():
        current = actual.get(key)
        if current is None:
            raise ValueError(f"missing frozen block: {key}")
        if current != expected:
            raise ValueError(f"frozen block hash mismatch: {key}")
