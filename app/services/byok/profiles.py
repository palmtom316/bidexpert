from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import redis
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal
from app.llm import default_model_for_role, get_fallback_chain, normalize_role
from app.models.tables import KeyStorage, ProjectModelPolicy, ProviderProfile, ProviderScope
from app.secrets.crypto import decrypt, encrypt, load_master_key


def _try_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError("invalid uuid") from exc


def _to_storage(value: str) -> KeyStorage:
    normalized = value.strip().upper()
    try:
        return KeyStorage[normalized]
    except KeyError as exc:
        raise ValueError("key_storage must be ENCRYPTED_DB|TEMP_REDIS|VAULT") from exc


def _redis_client() -> redis.Redis:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def _write_temp_key(secret_ref: str, api_key: str) -> None:
    _redis_client().set(secret_ref, api_key, ex=3600)


def _delete_temp_key(secret_ref: str) -> None:
    _redis_client().delete(secret_ref)


@dataclass
class ResolvedProfile:
    profile_id: str | None
    provider: str
    model: str
    api_key: str | None
    base_url: str | None


def _default_profile(task_type: str) -> ResolvedProfile:
    role = normalize_role(task_type)
    provider, model = default_model_for_role(role)
    return ResolvedProfile(None, provider, model, None, None)


def create_provider_profile(
    *,
    project_id: str,
    provider: str,
    base_url: str | None,
    default_model: str,
    api_key: str,
    key_storage: str,
    allowed_tasks: list[str],
    created_by: str | None = "system",
) -> ProviderProfile:
    project_uuid = _try_uuid(project_id)
    storage = _to_storage(key_storage)

    profile = ProviderProfile(
        scope=ProviderScope.PROJECT,
        scope_id=project_uuid,
        provider=provider.strip(),
        base_url=base_url.strip() if base_url else None,
        default_model=default_model.strip(),
        key_storage=storage,
        key_secret_ref=f"profile:{project_id}:{uuid.uuid4()}",
        encrypted_key=None,
        allowed_tasks=allowed_tasks or ["*"],
        created_by=created_by,
        updated_at=datetime.now(UTC),
    )

    if storage == KeyStorage.ENCRYPTED_DB:
        master_key = load_master_key()
        profile.encrypted_key = encrypt(api_key=api_key, master_key=master_key)
    elif storage == KeyStorage.TEMP_REDIS:
        try:
            _write_temp_key(profile.key_secret_ref, api_key)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("redis is unavailable for TEMP_REDIS storage") from exc
    elif storage == KeyStorage.VAULT:
        raise ValueError("VAULT is not configured yet")

    with SessionLocal() as db:
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


def list_provider_profiles(project_id: str) -> list[ProviderProfile]:
    project_uuid = _try_uuid(project_id)
    with SessionLocal() as db:
        stmt = select(ProviderProfile).where(
            ProviderProfile.scope == ProviderScope.PROJECT,
            ProviderProfile.scope_id == project_uuid,
        )
        return list(db.execute(stmt).scalars().all())


def get_provider_profile(profile_id: str) -> ProviderProfile | None:
    profile_uuid = _try_uuid(profile_id)
    with SessionLocal() as db:
        return db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_uuid)).scalar_one_or_none()


def delete_provider_profile(profile_id: str) -> bool:
    profile_uuid = _try_uuid(profile_id)
    with SessionLocal() as db:
        profile = db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_uuid)).scalar_one_or_none()
        if not profile:
            return False
        if profile.key_storage == KeyStorage.TEMP_REDIS:
            _delete_temp_key(profile.key_secret_ref)
        db.delete(profile)
        db.commit()
        return True


def _resolve_api_key(profile: ProviderProfile) -> str | None:
    try:
        if profile.key_storage == KeyStorage.ENCRYPTED_DB:
            if not profile.encrypted_key:
                return None
            master_key = load_master_key()
            return decrypt(profile.encrypted_key, master_key)
        if profile.key_storage == KeyStorage.TEMP_REDIS:
            value = _redis_client().get(profile.key_secret_ref)
            return value if isinstance(value, str) else None
        return None
    except Exception:  # noqa: BLE001
        return None


def _task_allowed(profile: ProviderProfile, task_type: str) -> bool:
    allowed = [str(item).upper() for item in (profile.allowed_tasks or ["*"])]
    return "*" in allowed or task_type.upper() in allowed


def upsert_project_model_policy(
    *,
    project_id: str,
    extract_profile_id: str | None,
    generate_profile_id: str | None,
    review_profile_id: str | None,
    embed_profile_id: str | None,
    query_rewrite_profile_id: str | None,
    program_support_profile_id: str | None,
    enable_review: bool,
    token_budget_total: int | None,
    concurrency_limits: dict | None,
) -> ProjectModelPolicy:
    project_uuid = _try_uuid(project_id)

    def _opt_uuid(value: str | None) -> uuid.UUID | None:
        return _try_uuid(value) if value else None

    with SessionLocal() as db:
        stmt = select(ProjectModelPolicy).where(ProjectModelPolicy.project_id == project_uuid)
        policy = db.execute(stmt).scalar_one_or_none()
        if not policy:
            policy = ProjectModelPolicy(project_id=project_uuid)

        policy.extract_profile_id = _opt_uuid(extract_profile_id)
        policy.generate_profile_id = _opt_uuid(generate_profile_id)
        policy.review_profile_id = _opt_uuid(review_profile_id)
        policy.embed_profile_id = _opt_uuid(embed_profile_id)
        policy.query_rewrite_profile_id = _opt_uuid(query_rewrite_profile_id)
        policy.program_support_profile_id = _opt_uuid(program_support_profile_id)
        policy.enable_review = enable_review
        if token_budget_total is not None:
            policy.token_budget_total = max(0, int(token_budget_total))
        if concurrency_limits:
            policy.concurrency_limits = concurrency_limits
        policy.updated_at = datetime.now(UTC)
        db.add(policy)
        db.commit()
        db.refresh(policy)
        return policy


def get_project_model_policy(project_id: str) -> ProjectModelPolicy | None:
    project_uuid = _try_uuid(project_id)
    with SessionLocal() as db:
        stmt = select(ProjectModelPolicy).where(ProjectModelPolicy.project_id == project_uuid)
        return db.execute(stmt).scalar_one_or_none()


def resolve_profile_for_task(project_id: str | None, task_type: str) -> ResolvedProfile:
    role = normalize_role(task_type)
    fallback_profile = _default_profile(role.value)
    if not project_id:
        return fallback_profile

    try:
        project_uuid = _try_uuid(project_id)
    except ValueError:
        return fallback_profile

    with SessionLocal() as db:
        policy = db.execute(
            select(ProjectModelPolicy).where(ProjectModelPolicy.project_id == project_uuid)
        ).scalar_one_or_none()
        if not policy:
            return fallback_profile

        profile_id: uuid.UUID | None
        if role.value == "EXTRACT":
            profile_id = policy.extract_profile_id
        elif role.value == "REVIEW":
            profile_id = policy.review_profile_id
        elif role.value == "EMBED":
            profile_id = policy.embed_profile_id
        elif role.value == "QUERY_REWRITE":
            profile_id = policy.query_rewrite_profile_id
        elif role.value == "PROGRAM_SUPPORT":
            profile_id = policy.program_support_profile_id
        else:
            profile_id = policy.generate_profile_id
        if not profile_id:
            return fallback_profile

        profile = db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_id)).scalar_one_or_none()
        if not profile:
            return fallback_profile
        if not _task_allowed(profile, role.value):
            return fallback_profile

    api_key = _resolve_api_key(profile)
    return ResolvedProfile(
        profile_id=str(profile.id),
        provider=profile.provider,
        model=profile.default_model,
        api_key=api_key,
        base_url=profile.base_url,
    )


def resolve_profile_chain_for_task(project_id: str | None, task_type: str) -> list[ResolvedProfile]:
    role = normalize_role(task_type)
    primary = resolve_profile_for_task(project_id=project_id, task_type=role.value)
    chain = [primary]
    seen = {(primary.provider.lower(), primary.model)}
    for provider, model in get_fallback_chain(role):
        key = (provider.lower(), model)
        if key in seen:
            continue
        chain.append(ResolvedProfile(None, provider, model, None, None))
        seen.add(key)
    return chain


def test_provider_profile(profile_id: str) -> tuple[ProviderProfile, bool, str]:
    profile = get_provider_profile(profile_id)
    if not profile:
        raise ValueError("provider profile not found")
    api_key = _resolve_api_key(profile)
    if not api_key:
        return profile, False, "missing credential"
    if not profile.base_url:
        return profile, True, "credential resolved"

    url = f"{profile.base_url.rstrip('/')}/chat/completions"
    body = {
        "model": profile.default_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        resp = httpx.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=10.0,
        )
        if 200 <= resp.status_code < 400:
            return profile, True, f"completion probe OK ({resp.status_code})"
        return profile, False, f"completion probe returned {resp.status_code}"
    except (httpx.HTTPError, OSError, TimeoutError, SQLAlchemyError) as exc:
        return profile, False, f"completion probe failed: {exc}"
