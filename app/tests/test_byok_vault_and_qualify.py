from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

from app.models.tables import KeyStorage
from app.services.adapters import ComplianceReviewResult, GenerationResult, ReviewResult
from app.services.byok import profiles


class _SessionStub:
    def __init__(self, profile=None):  # noqa: ANN001
        self.profile = profile
        self.deleted: list[object] = []

    def add(self, _obj) -> None:  # noqa: ANN001
        return None

    def commit(self) -> None:
        return None

    def refresh(self, _obj) -> None:  # noqa: ANN001
        return None

    def execute(self, _stmt):  # noqa: ANN001
        return SimpleNamespace(scalar_one_or_none=lambda: self.profile)

    def delete(self, obj) -> None:  # noqa: ANN001
        self.deleted.append(obj)


class _SessionCtx:
    def __init__(self, session: _SessionStub) -> None:
        self.session = session

    def __enter__(self) -> _SessionStub:
        return self.session

    def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
        del exc_type, exc, tb
        return False


def test_create_provider_profile_supports_vault_storage(monkeypatch) -> None:
    stored: dict[str, str] = {}
    session = _SessionStub()
    project_id = str(uuid.uuid4())

    monkeypatch.setattr(profiles, "_write_vault_key", lambda secret_ref, api_key: stored.setdefault(secret_ref, api_key))
    monkeypatch.setattr(profiles, "session_scope", lambda: _SessionCtx(session))

    profile = profiles.create_provider_profile(
        project_id=project_id,
        provider="openai",
        base_url="https://api.openai.com/v1",
        default_model="gpt-5",
        api_key="sk-vault",
        key_storage="VAULT",
        allowed_tasks=["REVIEW"],
        created_by="tester",
    )

    assert profile.key_storage == KeyStorage.VAULT
    assert stored[profile.key_secret_ref] == "sk-vault"
    assert profile.encrypted_key is None


def test_resolve_api_key_reads_from_vault(monkeypatch) -> None:
    profile = SimpleNamespace(key_storage=KeyStorage.VAULT, key_secret_ref="vault:path/1")
    monkeypatch.setattr(profiles, "_read_vault_key", lambda _secret_ref: "sk-from-vault")

    assert profiles._resolve_api_key(profile) == "sk-from-vault"  # noqa: SLF001


def test_delete_provider_profile_cleans_vault_secret(monkeypatch) -> None:
    profile = SimpleNamespace(key_storage=KeyStorage.VAULT, key_secret_ref="vault:path/2")
    session = _SessionStub(profile=profile)
    calls: list[str] = []

    monkeypatch.setattr(profiles, "_delete_vault_key", lambda secret_ref: calls.append(secret_ref))
    monkeypatch.setattr(profiles, "session_scope", lambda: _SessionCtx(session))

    deleted = profiles.delete_provider_profile(str(uuid.uuid4()))

    assert deleted is True
    assert calls == ["vault:path/2"]
    assert session.deleted == [profile]


def test_qualify_provider_profile_returns_quality_score(monkeypatch) -> None:
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        provider="openai",
        default_model="gpt-5",
        base_url="https://api.openai.com/v1",
    )

    class _Adapter:
        def generate(self, _payload):  # noqa: ANN001
            return GenerationResult(
                text="已生成",
                provider="openai",
                model="gpt-5",
                content_json={"content_blocks": [{"type": "paragraph", "text": "已生成", "evidence_ids": ["e-1"]}]},
            )

        def review(self, _payload):  # noqa: ANN001
            return ReviewResult(
                approved=True,
                issues=[],
                provider="openai",
                model="gpt-5",
                report={
                    "missing_requirements": [],
                    "logical_inconsistencies": [],
                    "risk_points": [],
                    "coverage_estimate": 1.0,
                    "score_estimate": 95.0,
                    "approved": True,
                    "issues": [],
                },
            )

        def compliance_review(self, _payload):  # noqa: ANN001
            return ComplianceReviewResult(
                status="PASS",
                report={"status": "PASS", "modeled_issues": [], "coverage_estimate": 0.95},
                provider="openai",
                model="gpt-5",
            )

    monkeypatch.setattr(profiles, "get_provider_profile", lambda _pid: profile)
    monkeypatch.setattr(profiles, "_resolve_api_key", lambda _profile: "sk-qualify")
    monkeypatch.setattr(profiles, "_completion_probe", lambda **_kwargs: (True, "completion probe OK (200)"))
    monkeypatch.setattr(profiles, "create_adapter", lambda _provider: _Adapter())

    _, report = profiles.qualify_provider_profile(str(profile.id))

    assert report["ready_for_online"] is True
    assert report["quality_score"] >= 80.0
    assert report["model_quality"]["score"] >= 80.0
    assert any(case["case_id"] == "review_contract" and case["passed"] for case in report["cases"])


def test_qualify_provider_profile_requires_credential(monkeypatch) -> None:
    profile = SimpleNamespace(
        id=uuid.uuid4(),
        provider="openai",
        default_model="gpt-5",
        base_url="https://api.openai.com/v1",
    )

    monkeypatch.setattr(profiles, "get_provider_profile", lambda _pid: profile)
    monkeypatch.setattr(profiles, "_resolve_api_key", lambda _profile: None)

    _, report = profiles.qualify_provider_profile(str(profile.id))

    assert report["ready_for_online"] is False
    assert report["quality_score"] < 60.0
    assert any(case["case_id"] == "credential_resolved" and not case["passed"] for case in report["cases"])


def test_write_vault_key_rejects_redis_fallback_in_prod(monkeypatch) -> None:
    class _RedisStub:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def set(self, secret_ref: str, api_key: str, ex: int | None = None) -> None:
            self.calls.append((secret_ref, api_key, ex))

    redis_stub = _RedisStub()
    monkeypatch.setattr(profiles, "_vault_enabled", lambda: False)
    monkeypatch.setattr(profiles, "_redis_client", lambda: redis_stub)
    monkeypatch.setattr(profiles.settings, "app_env", "prod", raising=False)
    monkeypatch.setattr(profiles.settings, "vault_redis_fallback_enabled", True, raising=False)

    try:
        profiles._write_vault_key("vault:path/prod", "sk-prod")  # noqa: SLF001
        assert False, "expected ValueError when redis fallback is enabled in prod"
    except ValueError as exc:
        assert "prod" in str(exc).lower()

    assert redis_stub.calls == []


def test_temp_and_vault_fallback_writes_share_same_ttl(monkeypatch) -> None:
    class _RedisStub:
        def __init__(self) -> None:
            self.calls: list[tuple] = []

        def set(self, secret_ref: str, api_key: str, ex: int | None = None) -> None:
            self.calls.append((secret_ref, api_key, ex))

    redis_stub = _RedisStub()
    monkeypatch.setattr(profiles, "_redis_client", lambda: redis_stub)
    monkeypatch.setattr(profiles, "_vault_enabled", lambda: False)
    monkeypatch.setattr(profiles.settings, "app_env", "dev", raising=False)
    monkeypatch.setattr(profiles.settings, "vault_redis_fallback_enabled", True, raising=False)

    profiles._write_temp_key("tmp:path/1", "sk-temp")  # noqa: SLF001
    profiles._write_vault_key("vault:path/dev", "sk-vault-fallback")  # noqa: SLF001

    assert len(redis_stub.calls) == 2
    first = redis_stub.calls[0]
    second = redis_stub.calls[1]
    assert first[2] is not None
    assert second[2] is not None
    assert first[2] == second[2]


def test_read_vault_key_logs_warning_when_using_redis_fallback(monkeypatch, caplog) -> None:
    class _RedisStub:
        def get(self, secret_ref: str) -> str | None:
            assert secret_ref == "vault:path/dev"
            return "sk-fallback"

    monkeypatch.setattr(profiles, "_vault_enabled", lambda: False)
    monkeypatch.setattr(profiles, "_vault_redis_fallback_allowed", lambda: True)
    monkeypatch.setattr(profiles, "_redis_client", lambda: _RedisStub())

    with caplog.at_level(logging.WARNING):
        value = profiles._read_vault_key("vault:path/dev")  # noqa: SLF001

    assert value == "sk-fallback"
    assert "redis fallback" in caplog.text.lower()


def test_test_provider_connection_requires_credential() -> None:
    ok, detail = profiles.test_provider_connection(
        provider="qwen",
        default_model="qwen3",
        api_key="",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert ok is False
    assert detail == "missing credential"


def test_test_provider_connection_resolves_global_base_url(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_probe(**kwargs):
        captured.update(kwargs)
        return True, "completion probe OK (200)"

    monkeypatch.setattr(profiles, "_completion_probe", _fake_probe)
    monkeypatch.setattr(
        profiles,
        "_global_credentials",
        lambda _provider: (None, "https://global.example/v1"),
    )

    ok, detail = profiles.test_provider_connection(
        provider="qwen",
        default_model="qwen3",
        api_key="sk-test",
        base_url=None,
    )

    assert ok is True
    assert detail == "completion probe OK (200)"
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://global.example/v1"
    profile = captured["profile"]
    assert profile.default_model == "qwen3"


def test_test_provider_connection_requires_base_url_when_no_fallback(monkeypatch) -> None:
    monkeypatch.setattr(profiles, "_global_credentials", lambda _provider: (None, None))

    ok, detail = profiles.test_provider_connection(
        provider="qwen",
        default_model="qwen3",
        api_key="sk-test",
        base_url=None,
    )

    assert ok is False
    assert detail == "missing base_url"
