from __future__ import annotations

_SYNONYM_GROUPS = [
    ("投标人", "供应商", "竞标人", "承包商"),
    ("资质", "资格", "资信"),
    ("业绩", "案例", "项目经验"),
    ("项目经理", "项目负责人"),
    ("变压器", "主变", "变电设备"),
    ("安全员", "安管人员", "安全管理人员"),
    ("评标", "评审", "评分"),
]

_SYNONYM_MAP: dict[str, tuple[str, ...]] = {}
for group in _SYNONYM_GROUPS:
    for item in group:
        alternatives = tuple(candidate for candidate in group if candidate != item)
        _SYNONYM_MAP[item] = alternatives


def expand_query_terms(query: str, *, max_expansions: int = 8) -> list[str]:
    raw = (query or "").strip()
    if not raw:
        return []
    limit = max(0, int(max_expansions))
    if limit == 0:
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    for key, synonyms in _SYNONYM_MAP.items():
        if key not in raw:
            continue
        for synonym in synonyms:
            if synonym in raw or synonym in seen:
                continue
            seen.add(synonym)
            candidates.append(synonym)
            if len(candidates) >= limit:
                return candidates
    return candidates


def expand_query_text(query: str, *, max_expansions: int = 8) -> str:
    raw = (query or "").strip()
    expansions = expand_query_terms(raw, max_expansions=max_expansions)
    if not expansions:
        return raw
    return " ".join([raw, *expansions]).strip()
