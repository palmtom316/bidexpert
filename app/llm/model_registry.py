from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.llm.roles import ModelRole, normalize_role


@dataclass(frozen=True)
class ModelRegistryEntry:
    provider: str
    model_name: str
    roles: tuple[str, ...]
    capabilities: tuple[str, ...]
    max_input_tokens: int
    supports_json_schema: bool
    supports_tool_calling: bool


@lru_cache(maxsize=1)
def _load_registry_payload() -> dict:
    config_dir = Path(__file__).resolve().parent.parent / "config"
    candidate_paths = [
        config_dir / "model_registry.json",
        config_dir / "model_registry.yaml",  # backward compatibility
    ]
    for registry_path in candidate_paths:
        if not registry_path.exists():
            continue
        raw = registry_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("model registry payload must be an object")
        return payload
    raise ValueError("model registry file is missing")


@lru_cache(maxsize=1)
def list_registry_entries() -> tuple[ModelRegistryEntry, ...]:
    payload = _load_registry_payload()
    models = payload.get("models", [])
    if not isinstance(models, list):
        raise ValueError("model registry models must be a list")

    result: list[ModelRegistryEntry] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider", "")).strip().lower()
        model_name = str(item.get("model_name", "")).strip()
        if not provider or not model_name:
            continue
        roles = tuple(str(role).strip().upper() for role in (item.get("roles") or []))
        capabilities = tuple(str(cap).strip().lower() for cap in (item.get("capabilities") or []))
        result.append(
            ModelRegistryEntry(
                provider=provider,
                model_name=model_name,
                roles=roles,
                capabilities=capabilities,
                max_input_tokens=int(item.get("max_input_tokens") or 0),
                supports_json_schema=bool(item.get("supports_json_schema")),
                supports_tool_calling=bool(item.get("supports_tool_calling")),
            )
        )
    return tuple(result)


def _parse_provider_model(token: str) -> tuple[str, str] | None:
    if ":" not in token:
        return None
    provider, model = token.split(":", maxsplit=1)
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        return None
    return provider, model


def get_fallback_chain(role: str | ModelRole) -> list[tuple[str, str]]:
    resolved_role = normalize_role(role.value if isinstance(role, ModelRole) else str(role))
    payload = _load_registry_payload()
    role_defaults = payload.get("role_defaults", {})
    if not isinstance(role_defaults, dict):
        role_defaults = {}

    raw_chain = role_defaults.get(resolved_role.value, [])
    chain: list[tuple[str, str]] = []
    if isinstance(raw_chain, list):
        for token in raw_chain:
            parsed = _parse_provider_model(str(token))
            if parsed:
                chain.append(parsed)

    if chain:
        return chain

    candidates = [
        (entry.provider, entry.model_name)
        for entry in list_registry_entries()
        if resolved_role.value in entry.roles
    ]
    return candidates


def default_model_for_role(role: str | ModelRole) -> tuple[str, str]:
    chain = get_fallback_chain(role)
    if chain:
        return chain[0]
    return "qwen", "qwen3"


def get_registry_entry(provider: str, model_name: str) -> ModelRegistryEntry | None:
    normalized_provider = (provider or "").strip().lower()
    normalized_model = (model_name or "").strip()
    for item in list_registry_entries():
        if item.provider == normalized_provider and item.model_name == normalized_model:
            return item
    return None


def list_models_for_role(role: str | ModelRole) -> list[ModelRegistryEntry]:
    resolved_role = normalize_role(role.value if isinstance(role, ModelRole) else str(role))
    return [item for item in list_registry_entries() if resolved_role.value in item.roles]


__all__ = [
    "ModelRegistryEntry",
    "default_model_for_role",
    "get_fallback_chain",
    "get_registry_entry",
    "list_models_for_role",
    "list_registry_entries",
]
