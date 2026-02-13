from __future__ import annotations

import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def embed_text(text: str, vector_size: int = 256) -> list[float]:
    vec = [0.0] * vector_size
    tokens = TOKEN_PATTERN.findall(text.lower())
    if not tokens:
        return vec

    for token in tokens:
        digest = hashlib.sha1(token.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % vector_size
        sign = 1.0 if (int(digest[8:10], 16) % 2 == 0) else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return vec
    return [x / norm for x in vec]
