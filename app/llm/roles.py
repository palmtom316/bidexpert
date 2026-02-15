from __future__ import annotations

from enum import StrEnum


class ModelRole(StrEnum):
    EXTRACT = "EXTRACT"
    EMBED = "EMBED"
    GENERATE = "GENERATE"
    REVIEW = "REVIEW"
    QUERY_REWRITE = "QUERY_REWRITE"
    PROGRAM_SUPPORT = "PROGRAM_SUPPORT"


ROLE_ALIASES = {
    "SECTION_GENERATE": ModelRole.GENERATE.value,
    "GENERATE_DRAFT": ModelRole.GENERATE.value,
    "SECTION_REVIEW": ModelRole.REVIEW.value,
    "REQUIREMENT_EXTRACT": ModelRole.EXTRACT.value,
    "EXTRACT_HISTORICAL": ModelRole.EXTRACT.value,
    "QUERY_REWRITE": ModelRole.QUERY_REWRITE.value,
    "REWRITE_QUERY": ModelRole.QUERY_REWRITE.value,
    "EMBEDDING": ModelRole.EMBED.value,
}


def normalize_role(task_type: str) -> ModelRole:
    raw = (task_type or "").strip().upper()
    normalized = ROLE_ALIASES.get(raw, raw)
    try:
        return ModelRole(normalized)
    except ValueError:
        return ModelRole.GENERATE


ALL_MODEL_ROLES = tuple(item.value for item in ModelRole)

