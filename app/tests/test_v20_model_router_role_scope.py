from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.llm.model_registry import normalize_role_scope
from app.services.adapters.base import ComplianceReviewRequest, QueryRewriteRequest
from app.services.adapters import providers as providers_module
from app.services.adapters.providers import OpenAICompatibleAdapter
from app.services.byok import profiles


def test_role_scope_routes_to_extract_profile(monkeypatch) -> None:
    project_id = str(uuid.uuid4())
    extract_profile_id = uuid.uuid4()
    fallback = profiles.ResolvedProfile(None, "openai", "gpt-5", None, None)

    policy = SimpleNamespace(
        extract_profile_id=extract_profile_id,
        generate_profile_id=None,
        review_profile_id=None,
        embed_profile_id=None,
        query_rewrite_profile_id=None,
        program_support_profile_id=None,
        rerank_profile_id=None,
    )
    profile = SimpleNamespace(
        id=extract_profile_id,
        provider="qwen",
        default_model="qwen3.5",
        base_url="https://router.example/v1",
        allowed_tasks=["EXTRACT"],
    )

    class _DbStub:
        def __init__(self) -> None:
            self._count = 0

        def execute(self, _stmt):  # noqa: ANN001
            self._count += 1
            if self._count == 1:
                return SimpleNamespace(scalar_one_or_none=lambda: policy)
            return SimpleNamespace(scalar_one_or_none=lambda: profile)

    class _Ctx:
        def __init__(self, db) -> None:  # noqa: ANN001
            self.db = db

        def __enter__(self):  # noqa: ANN204
            return self.db

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001
            del exc_type, exc, tb
            return False

    monkeypatch.setattr(profiles, "_default_profile", lambda _task_type: fallback)
    monkeypatch.setattr(profiles, "session_scope", lambda: _Ctx(_DbStub()))
    monkeypatch.setattr(profiles, "_task_allowed", lambda _profile, _task_type: True)
    monkeypatch.setattr(profiles, "_resolve_api_key", lambda _profile: "sk-extract")
    monkeypatch.setattr(profiles, "_global_credentials", lambda _provider: (None, None))

    resolved = profiles.resolve_profile_for_task(
        project_id=project_id,
        task_type="GENERATE",
        role_scope="extract.json",
    )
    assert resolved.profile_id == str(extract_profile_id)
    assert resolved.provider == "qwen"


def test_normalize_role_scope_maps_extract_json_to_extract() -> None:
    assert normalize_role_scope("extract.json").value == "EXTRACT"
    assert normalize_role_scope("review").value == "REVIEW"
    assert normalize_role_scope("SECTION_GENERATE").value == "GENERATE"


def test_resolve_profile_backward_compat_uses_task_type_alias(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _fake_default(task_type: str):  # noqa: ANN001
        captured["task_type"] = task_type
        return profiles.ResolvedProfile(None, "qwen", "qwen3.5", None, None)

    monkeypatch.setattr(profiles, "_default_profile", _fake_default)
    resolved = profiles.resolve_profile_for_task(project_id=None, task_type="SECTION_GENERATE")

    assert captured["task_type"] == "GENERATE"
    assert resolved.provider == "qwen"


def test_provider_structured_calls_force_json_object(monkeypatch) -> None:
    adapter = OpenAICompatibleAdapter("qwen")
    captured_calls: list[dict] = []

    def _fake_post_chat(**kwargs):  # noqa: ANN003
        captured_calls.append(kwargs)
        if "rewritten_query" in kwargs.get("prompt", ""):
            return '{"rewritten_query":"ok"}'
        return '{"status":"PASS","modeled_issues":[],"general_comments":"ok"}'

    monkeypatch.setattr(adapter, "_post_chat", _fake_post_chat)

    adapter.compliance_review(
        ComplianceReviewRequest(
            model="qwen3.5",
            content_text="text",
            requirements=[{"requirement_code": "R-1", "strength": "MUST", "original_text": "x"}],
            api_key="sk",
            base_url="https://example.com/v1",
        )
    )
    adapter.rewrite_query(
        QueryRewriteRequest(
            model="qwen3.5",
            query="原始问题",
            api_key="sk",
            base_url="https://example.com/v1",
        )
    )

    assert captured_calls[0]["response_format"] == {"type": "json_object"}
    assert captured_calls[1]["response_format"] == {"type": "json_object"}


def test_provider_retries_without_response_format_when_unsupported(monkeypatch) -> None:
    adapter = OpenAICompatibleAdapter("qwen")
    sent_bodies: list[dict] = []

    class _Response:
        def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
            self.status_code = status_code
            self._payload = payload
            self.text = text

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise providers_module.httpx.HTTPStatusError(
                    "bad request",
                    request=providers_module.httpx.Request("POST", "https://example.com"),
                    response=self,
                )

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self) -> None:
            self.count = 0

        def post(self, _url: str, *, headers: dict, json: dict):  # noqa: A002
            del headers
            sent_bodies.append(dict(json))
            self.count += 1
            if self.count == 1:
                return _Response(400, {}, text="unsupported response_format")
            return _Response(
                200,
                {"choices": [{"message": {"content": '{"status":"PASS","modeled_issues":[],"general_comments":"ok"}'}}]},
            )

    monkeypatch.setattr(providers_module, "_shared_http_client", lambda _timeout: _Client())

    adapter.compliance_review(
        ComplianceReviewRequest(
            model="qwen3.5",
            content_text="text",
            requirements=[{"requirement_code": "R-1", "strength": "MUST", "original_text": "x"}],
            api_key="sk",
            base_url="https://example.com/v1",
        )
    )

    assert "response_format" in sent_bodies[0]
    assert "response_format" not in sent_bodies[1]
