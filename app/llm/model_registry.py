from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def _config_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "config"


def _resolve_registry_path() -> Path:
    override = (os.getenv("MODEL_REGISTRY_PATH") or os.getenv("BIDEXPERT_MODEL_REGISTRY_PATH") or "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = Path.cwd() / path
        if not path.exists():
            raise ValueError(f"model registry file not found: {path}")
        return path

    candidate_paths = [
        _config_dir() / "model_registry.json",
        _config_dir() / "model_registry.yaml",  # backward compatibility
    ]
    for registry_path in candidate_paths:
        if registry_path.exists():
            return registry_path

    raise ValueError("model registry file is missing")


@lru_cache(maxsize=8)
def _load_registry_payload_from_path(path: str) -> dict:
    raw = Path(path).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("model registry payload must be an object")
    return payload


def _load_registry_payload() -> dict:
    registry_path = _resolve_registry_path()
    return _load_registry_payload_from_path(str(registry_path))


def clear_model_registry_cache() -> None:
    _load_registry_payload_from_path.cache_clear()
    list_registry_entries.cache_clear()


def _parse_provider_model(token: str) -> tuple[str, str] | None:
    if ":" not in token:
        return None
    provider, model = token.split(":", maxsplit=1)
    provider = provider.strip().lower()
    model = model.strip()
    if not provider or not model:
        return None
    return provider, model


def _parse_provider_model_item(item: Any) -> tuple[str, str] | None:
    if isinstance(item, dict):
        provider = str(item.get("provider", "")).strip().lower()
        model = str(item.get("model", item.get("model_name", ""))).strip()
        if provider and model:
            return provider, model
        return None
    if isinstance(item, str):
        return _parse_provider_model(item)
    return None


def _cn_role_chain(payload: dict[str, Any], resolved_role: ModelRole) -> list[tuple[str, str]]:
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        return []

    role_payload: dict[str, Any] | None = None
    for key, value in roles.items():
        if str(key).strip().upper() == resolved_role.value and isinstance(value, dict):
            role_payload = value
            break

    if not role_payload:
        return []

    chain: list[tuple[str, str]] = []
    primary = _parse_provider_model_item(role_payload.get("primary"))
    if primary:
        chain.append(primary)

    fallback = role_payload.get("fallback")
    if isinstance(fallback, list):
        for item in fallback:
            parsed = _parse_provider_model_item(item)
            if parsed:
                chain.append(parsed)

    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for provider, model in chain:
        key = (provider.lower(), model)
        if key in seen:
            continue
        seen.add(key)
        deduped.append((provider, model))
    return deduped


def _entries_from_models_payload(payload: dict[str, Any]) -> list[ModelRegistryEntry]:
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
    return result


def _entries_from_cn_roles_payload(payload: dict[str, Any]) -> list[ModelRegistryEntry]:
    roles = payload.get("roles")
    if not isinstance(roles, dict):
        return []

    role_mapping: dict[tuple[str, str], set[str]] = {}
    for role_key, role_payload in roles.items():
        if not isinstance(role_payload, dict):
            continue
        role_name = normalize_role(str(role_key)).value

        candidates: list[tuple[str, str]] = []
        primary = _parse_provider_model_item(role_payload.get("primary"))
        if primary:
            candidates.append(primary)
        fallback = role_payload.get("fallback")
        if isinstance(fallback, list):
            for item in fallback:
                parsed = _parse_provider_model_item(item)
                if parsed:
                    candidates.append(parsed)

        for provider, model_name in candidates:
            key = (provider.lower(), model_name)
            role_mapping.setdefault(key, set()).add(role_name)

    result: list[ModelRegistryEntry] = []
    for (provider, model_name), role_names in sorted(role_mapping.items(), key=lambda item: item[0]):
        result.append(
            ModelRegistryEntry(
                provider=provider,
                model_name=model_name,
                roles=tuple(sorted(role_names)),
                capabilities=(),
                max_input_tokens=0,
                supports_json_schema=False,
                supports_tool_calling=False,
            )
        )
    return result


@lru_cache(maxsize=1)
def list_registry_entries() -> tuple[ModelRegistryEntry, ...]:
    payload = _load_registry_payload()

    entries = _entries_from_models_payload(payload)
    if entries:
        return tuple(entries)

    return tuple(_entries_from_cn_roles_payload(payload))


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

    cn_chain = _cn_role_chain(payload, resolved_role)
    if cn_chain:
        return cn_chain

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
    return "qwen", "qwen3.5"


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


def get_provider_runtime_config(provider: str) -> dict[str, Any]:
    normalized_provider = (provider or "").strip().lower()
    if not normalized_provider:
        return {}

    payload = _load_registry_payload()
    providers = payload.get("providers")
    if not isinstance(providers, dict):
        return {}

    for key, value in providers.items():
        if str(key).strip().lower() != normalized_provider:
            continue
        if not isinstance(value, dict):
            return {}
        return dict(value)
    return {}


def model_registry_source_path() -> str:
    return str(_resolve_registry_path())


def current_registry_mode() -> str:
    payload = _load_registry_payload()
    version = str(payload.get("version", "")).strip().lower()
    if "debug" in version:
        return "debug"
    if "prod" in version:
        return "prod"

    filename = _resolve_registry_path().name.lower()
    if "debug" in filename:
        return "debug"
    if "prod" in filename:
        return "prod"

    return "prod"


__all__ = [
    "ModelRegistryEntry",
    "clear_model_registry_cache",
    "current_registry_mode",
    "default_model_for_role",
    "get_fallback_chain",
    "get_provider_runtime_config",
    "get_registry_entry",
    "list_models_for_role",
    "list_registry_entries",
    "model_registry_source_path",
]
