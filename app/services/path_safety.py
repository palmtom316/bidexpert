from __future__ import annotations

import re

_SAFE_PATH_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def validate_path_identifier(name: str, raw: str) -> str:
    token = (raw or "").strip()
    if not token or not _SAFE_PATH_IDENTIFIER.fullmatch(token):
        raise ValueError(f"invalid {name}")
    return token
