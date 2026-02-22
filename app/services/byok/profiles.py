from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import redis
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import normalized_app_env, settings
from app.db.session import session_scope
from app.llm import default_model_for_role, get_fallback_chain, normalize_role
from app.models.tables import KeyStorage, ProjectModelPolicy, ProviderProfile, ProviderScope
from app.secrets.crypto import decrypt, encrypt, load_master_key
from app.services.adapters import (
    AdapterUnavailableError,
    ComplianceReviewRequest,
    GenerationRequest,
    ReviewRequest,
    create_adapter,
)
from app.services.model_quality import evaluate_compliance_quality


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


def _secret_ttl_seconds() -> int:
    return max(1, int(settings.secret_temp_key_ttl_seconds))


def _vault_redis_fallback_allowed() -> bool:
    if not settings.vault_redis_fallback_enabled:
        return False
    return normalized_app_env() != "prod"


def _write_temp_key(secret_ref: str, api_key: str) -> None:
    _redis_client().set(secret_ref, api_key, ex=_secret_ttl_seconds())


def _delete_temp_key(secret_ref: str) -> None:
    _redis_client().delete(secret_ref)


def _vault_enabled() -> bool:
    return bool((settings.vault_addr or "").strip() and (settings.vault_token or "").strip())


def _vault_path(secret_ref: str) -> str:
    raw = str(secret_ref or "").strip()
    if raw.startswith("vault:"):
        raw = raw[6:]
    return raw.lstrip("/")


def _vault_headers() -> dict[str, str]:
    headers = {
        "X-Vault-Token": str(settings.vault_token or "").strip(),
        "Content-Type": "application/json",
    }
    namespace = str(settings.vault_namespace or "").strip()
    if namespace:
        headers["X-Vault-Namespace"] = namespace
    return headers


def _vault_data_url(secret_ref: str) -> str:
    base = str(settings.vault_addr or "").strip().rstrip("/")
    mount = str(settings.vault_mount or "secret").strip().strip("/")
    return f"{base}/v1/{mount}/data/{_vault_path(secret_ref)}"


def _write_vault_key(secret_ref: str, api_key: str) -> None:
    if _vault_enabled():
        resp = httpx.post(
            _vault_data_url(secret_ref),
            headers=_vault_headers(),
            json={"data": {"api_key": api_key}},
            timeout=10.0,
        )
        resp.raise_for_status()
        return
    if not settings.vault_redis_fallback_enabled:
        raise ValueError("vault is not configured")
    if normalized_app_env() == "prod":
        raise ValueError("vault redis fallback is disabled in prod")
    _redis_client().set(secret_ref, api_key, ex=_secret_ttl_seconds())


def _read_vault_key(secret_ref: str) -> str | None:
    if _vault_enabled():
        resp = httpx.get(
            _vault_data_url(secret_ref),
            headers=_vault_headers(),
            timeout=10.0,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        nested = data.get("data") if isinstance(data, dict) else {}
        value = nested.get("api_key") if isinstance(nested, dict) else None
        return value if isinstance(value, str) else None
    if not _vault_redis_fallback_allowed():
        return None
    value = _redis_client().get(secret_ref)
    return value if isinstance(value, str) else None


def _delete_vault_key(secret_ref: str) -> None:
    if _vault_enabled():
        resp = httpx.delete(
            _vault_data_url(secret_ref),
            headers=_vault_headers(),
            timeout=10.0,
        )
        if resp.status_code not in {200, 204, 404}:
            resp.raise_for_status()
        return
    if _vault_redis_fallback_allowed():
        _redis_client().delete(secret_ref)


@dataclass
class ResolvedProfile:
    profile_id: str | None
    provider: str
    model: str
    api_key: str | None
    base_url: str | None


def _global_credentials(provider: str) -> tuple[str | None, str | None]:
    normalized = (provider or "").strip().lower()
    if normalized == "openai":
        return (
            settings.openai_api_key or os.getenv("OPENAI_API_KEY"),
            settings.openai_base_url or os.getenv("OPENAI_BASE_URL"),
        )
    if normalized == "gemini":
        return (
            settings.gemini_api_key or os.getenv("GEMINI_API_KEY"),
            settings.gemini_base_url or os.getenv("GEMINI_BASE_URL"),
        )
    if normalized == "qwen":
        return (
            settings.qwen_api_key or os.getenv("QWEN_API_KEY"),
            settings.qwen_base_url or os.getenv("QWEN_BASE_URL"),
        )
    if normalized == "deepseek":
        return (
            settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY"),
            settings.deepseek_base_url or os.getenv("DEEPSEEK_BASE_URL"),
        )
    if normalized == "voyage":
        return (
            settings.voyage_api_key or os.getenv("VOYAGE_API_KEY"),
            settings.voyage_base_url or os.getenv("VOYAGE_BASE_URL"),
        )
    return None, None


def _default_profile(task_type: str) -> ResolvedProfile:
    role = normalize_role(task_type)
    provider, model = default_model_for_role(role)
    api_key, base_url = _global_credentials(provider)
    return ResolvedProfile(None, provider, model, api_key, base_url)


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
    if storage == KeyStorage.VAULT:
        secret_ref = f"vault:profiles/{project_id}/{uuid.uuid4()}"
    else:
        secret_ref = f"profile:{project_id}:{uuid.uuid4()}"

    profile = ProviderProfile(
        scope=ProviderScope.PROJECT,
        scope_id=project_uuid,
        provider=provider.strip(),
        base_url=base_url.strip() if base_url else None,
        default_model=default_model.strip(),
        key_storage=storage,
        key_secret_ref=secret_ref,
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
        try:
            _write_vault_key(profile.key_secret_ref, api_key)
        except Exception as exc:  # noqa: BLE001
            raise ValueError("vault is unavailable for VAULT storage") from exc

    with session_scope() as db:
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


def list_provider_profiles(project_id: str) -> list[ProviderProfile]:
    project_uuid = _try_uuid(project_id)
    with session_scope() as db:
        stmt = select(ProviderProfile).where(
            ProviderProfile.scope == ProviderScope.PROJECT,
            ProviderProfile.scope_id == project_uuid,
        )
        return list(db.execute(stmt).scalars().all())


def get_provider_profile(profile_id: str) -> ProviderProfile | None:
    profile_uuid = _try_uuid(profile_id)
    with session_scope() as db:
        return db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_uuid)).scalar_one_or_none()


def delete_provider_profile(profile_id: str) -> bool:
    profile_uuid = _try_uuid(profile_id)
    with session_scope() as db:
        profile = db.execute(select(ProviderProfile).where(ProviderProfile.id == profile_uuid)).scalar_one_or_none()
        if not profile:
            return False
        if profile.key_storage == KeyStorage.TEMP_REDIS:
            _delete_temp_key(profile.key_secret_ref)
        elif profile.key_storage == KeyStorage.VAULT:
            _delete_vault_key(profile.key_secret_ref)
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
        if profile.key_storage == KeyStorage.VAULT:
            return _read_vault_key(profile.key_secret_ref)
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
    rerank_profile_id: str | None,
    query_rewrite_profile_id: str | None,
    program_support_profile_id: str | None,
    enable_review: bool,
    token_budget_total: int | None,
    concurrency_limits: dict | None,
) -> ProjectModelPolicy:
    project_uuid = _try_uuid(project_id)

    def _opt_uuid(value: str | None) -> uuid.UUID | None:
        return _try_uuid(value) if value else None

    with session_scope() as db:
        stmt = select(ProjectModelPolicy).where(ProjectModelPolicy.project_id == project_uuid)
        policy = db.execute(stmt).scalar_one_or_none()
        if not policy:
            policy = ProjectModelPolicy(project_id=project_uuid)

        policy.extract_profile_id = _opt_uuid(extract_profile_id)
        policy.generate_profile_id = _opt_uuid(generate_profile_id)
        policy.review_profile_id = _opt_uuid(review_profile_id)
        policy.embed_profile_id = _opt_uuid(embed_profile_id)
        policy.rerank_profile_id = _opt_uuid(rerank_profile_id)
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
    with session_scope() as db:
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

    with session_scope() as db:
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
        elif role.value == "RERANK":
            profile_id = policy.rerank_profile_id
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
    global_api_key, global_base_url = _global_credentials(profile.provider)
    return ResolvedProfile(
        profile_id=str(profile.id),
        provider=profile.provider,
        model=profile.default_model,
        api_key=api_key or global_api_key,
        base_url=profile.base_url or global_base_url,
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
        api_key, base_url = _global_credentials(provider)
        chain.append(ResolvedProfile(None, provider, model, api_key, base_url))
        seen.add(key)
    return chain


def _completion_probe(
    *,
    profile: ProviderProfile | SimpleNamespace,
    api_key: str,
    base_url: str | None = None,
) -> tuple[bool, str]:
    target_base_url = (base_url or profile.base_url or "").strip()
    if not target_base_url:
        return True, "credential resolved"

    url = f"{target_base_url.rstrip('/')}/chat/completions"
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
            return True, f"completion probe OK ({resp.status_code})"
        return False, f"completion probe returned {resp.status_code}"
    except (httpx.HTTPError, OSError, TimeoutError, SQLAlchemyError) as exc:
        return False, f"completion probe failed: {exc}"


def test_provider_profile(profile_id: str) -> tuple[ProviderProfile, bool, str]:
    profile = get_provider_profile(profile_id)
    if not profile:
        raise ValueError("provider profile not found")
    api_key = _resolve_api_key(profile)
    global_api_key, global_base_url = _global_credentials(profile.provider)
    effective_key = api_key or global_api_key
    effective_base_url = profile.base_url or global_base_url
    if not effective_key:
        return profile, False, "missing credential"
    ok, detail = _completion_probe(profile=profile, api_key=effective_key, base_url=effective_base_url)
    return profile, ok, detail


def _qualify_case(
    *,
    case_id: str,
    name: str,
    weight: float,
    passed: bool,
    detail: str,
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "name": name,
        "weight": float(weight),
        "passed": bool(passed),
        "detail": detail,
    }


def qualify_provider_profile(
    profile_id: str,
    *,
    score_threshold: float = 80.0,
) -> tuple[ProviderProfile, dict[str, Any]]:
    profile = get_provider_profile(profile_id)
    if not profile:
        raise ValueError("provider profile not found")

    profile_api_key = _resolve_api_key(profile)
    global_api_key, global_base_url = _global_credentials(profile.provider)
    effective_api_key = profile_api_key or global_api_key
    effective_base_url = profile.base_url or global_base_url
    try:
        adapter = create_adapter(profile.provider)
    except AdapterUnavailableError as exc:
        raise ValueError(str(exc)) from exc

    cases: list[dict[str, Any]] = []
    credential_passed = bool(effective_api_key)
    credential_detail = "credential resolved" if credential_passed else "missing credential"
    if profile_api_key and global_api_key and profile_api_key != global_api_key:
        credential_detail = "credential resolved (profile overrides global)"
    elif profile_api_key:
        credential_detail = "credential resolved (profile storage)"
    elif global_api_key:
        credential_detail = "credential resolved (global credential fallback)"
    cases.append(
        _qualify_case(
            case_id="credential_resolved",
            name="Credential Resolved",
            weight=20.0,
            passed=credential_passed,
            detail=credential_detail,
        )
    )

    if credential_passed:
        probe_profile = SimpleNamespace(
            base_url=effective_base_url,
            default_model=profile.default_model,
        )
        probe_ok, probe_detail = _completion_probe(
            profile=probe_profile,
            api_key=str(effective_api_key),
            base_url=effective_base_url,
        )
    else:
        probe_ok, probe_detail = False, "skipped: missing credential"
    cases.append(
        _qualify_case(
            case_id="completion_probe",
            name="Completion Probe",
            weight=15.0,
            passed=probe_ok,
            detail=probe_detail,
        )
    )

    generation_ok = False
    generation_detail = "skipped: probe failed"
    if credential_passed and probe_ok:
        try:
            generated = adapter.generate(
                GenerationRequest(
                    model=profile.default_model,
                    requirement_text="验证模型基础生成能力",
                    evidence_texts=["证据片段 A"],
                    evidence_ids=["e-1"],
                    global_facts={},
                    relevant_requirements=["验证模型基础生成能力"],
                    relevant_scoring=[],
                    top_chunks=[],
                    api_key=effective_api_key,
                    base_url=effective_base_url,
                )
            )
            generation_ok = bool(str(generated.text or "").strip())
            generation_detail = "generation contract ok" if generation_ok else "generation returned empty text"
        except Exception as exc:  # noqa: BLE001
            generation_detail = f"generation contract failed: {exc}"
    cases.append(
        _qualify_case(
            case_id="generation_contract",
            name="Generation Contract",
            weight=20.0,
            passed=generation_ok,
            detail=generation_detail,
        )
    )

    review_ok = False
    review_detail = "skipped: probe failed"
    review_score_estimate = 0.0
    if credential_passed and probe_ok:
        try:
            reviewed = adapter.review(
                ReviewRequest(
                    model=profile.default_model,
                    draft_text="本段用于验证 review contract。",
                    evidence_texts=["证据片段 A"],
                    api_key=effective_api_key,
                    base_url=effective_base_url,
                )
            )
            review_payload = reviewed.report if isinstance(reviewed.report, dict) else {}
            review_ok = (
                isinstance(review_payload.get("missing_requirements", []), list)
                and isinstance(review_payload.get("logical_inconsistencies", []), list)
                and isinstance(review_payload.get("risk_points", []), list)
            )
            try:
                review_score_estimate = max(0.0, min(100.0, float(review_payload.get("score_estimate", 0.0))))
            except (TypeError, ValueError):
                review_score_estimate = 0.0
            review_detail = "review contract ok" if review_ok else "review payload missing required fields"
        except Exception as exc:  # noqa: BLE001
            review_detail = f"review contract failed: {exc}"
    cases.append(
        _qualify_case(
            case_id="review_contract",
            name="Review Contract",
            weight=20.0,
            passed=review_ok,
            detail=review_detail,
        )
    )

    compliance_ok = False
    compliance_detail = "skipped: probe failed"
    compliance_quality_score = 0.0
    if credential_passed and probe_ok:
        try:
            compliance = adapter.compliance_review(
                ComplianceReviewRequest(
                    model=profile.default_model,
                    content_text="本段用于验证 compliance contract。",
                    requirements=[
                        {
                            "requirement_code": "QUALIFY-1",
                            "strength": "MUST",
                            "original_text": "内容需可验证。",
                        }
                    ],
                    api_key=effective_api_key,
                    base_url=effective_base_url,
                )
            )
            compliance_payload = compliance.report if isinstance(compliance.report, dict) else {}
            compliance_ok = (
                str(compliance.status).upper() in {"PASS", "WARN", "FAIL"}
                and isinstance(compliance_payload.get("modeled_issues", []), list)
            )
            compliance_quality_score = evaluate_compliance_quality(
                status=str(compliance.status),
                report=compliance_payload,
            )
            compliance_detail = "compliance contract ok" if compliance_ok else "compliance payload invalid"
        except Exception as exc:  # noqa: BLE001
            compliance_detail = f"compliance contract failed: {exc}"
    cases.append(
        _qualify_case(
            case_id="compliance_contract",
            name="Compliance Contract",
            weight=25.0,
            passed=compliance_ok,
            detail=compliance_detail,
        )
    )

    total_weight = sum(float(case["weight"]) for case in cases)
    passed_weight = sum(float(case["weight"]) for case in cases if bool(case["passed"]))
    capability_score = round((passed_weight / total_weight) * 100.0, 2) if total_weight > 0 else 0.0

    quality_components = [item for item in [review_score_estimate, compliance_quality_score] if item > 0]
    model_quality_score = (
        round(sum(quality_components) / len(quality_components), 2) if quality_components else 0.0
    )
    quality_score = round(capability_score * 0.75 + model_quality_score * 0.25, 2)

    passed_lookup = {str(case["case_id"]): bool(case["passed"]) for case in cases}
    must_pass = {
        "credential_resolved",
        "completion_probe",
        "review_contract",
        "compliance_contract",
    }
    ready_for_online = quality_score >= float(score_threshold) and all(
        passed_lookup.get(case_id, False) for case_id in must_pass
    )

    return profile, {
        "ready_for_online": ready_for_online,
        "threshold": float(score_threshold),
        "quality_score": quality_score,
        "capability_score": capability_score,
        "model_quality": {
            "score": model_quality_score,
            "review_score_estimate": round(review_score_estimate, 2),
            "compliance_quality_score": round(compliance_quality_score, 2),
        },
        "cases": cases,
    }
