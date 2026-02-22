from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.api import routes
from app.schemas.contracts import ProjectModelPolicyUpsertRequest
from app.services.byok import profiles


def test_put_model_policy_forwards_rerank_profile_id(monkeypatch) -> None:
    project_id = str(uuid.uuid4())
    rerank_profile_id = str(uuid.uuid4())
    captured: dict[str, object] = {}

    def _fake_upsert(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return SimpleNamespace(
            project_id=uuid.UUID(project_id),
            extract_profile_id=None,
            generate_profile_id=None,
            review_profile_id=None,
            embed_profile_id=None,
            query_rewrite_profile_id=None,
            program_support_profile_id=None,
            rerank_profile_id=uuid.UUID(rerank_profile_id),
            enable_review=True,
            token_budget_total=500000,
            token_budget_used=0,
            concurrency_limits={"extract": 2, "generate": 3, "review": 2, "embed": 2, "query_rewrite": 2, "program_support": 1, "rerank": 2},
        )

    monkeypatch.setattr(routes, "upsert_project_model_policy", _fake_upsert)

    payload = ProjectModelPolicyUpsertRequest(rerank_profile_id=rerank_profile_id)
    response = routes.put_model_policy_api(project_id, payload)

    assert captured["rerank_profile_id"] == rerank_profile_id
    assert response.rerank_profile_id == rerank_profile_id


def test_resolve_profile_for_task_uses_rerank_profile_id(monkeypatch) -> None:
    project_id = str(uuid.uuid4())
    profile_id = uuid.uuid4()
    fallback = profiles.ResolvedProfile(None, "openai", "gpt-5", None, None)

    policy = SimpleNamespace(
        extract_profile_id=None,
        generate_profile_id=None,
        review_profile_id=None,
        embed_profile_id=None,
        query_rewrite_profile_id=None,
        program_support_profile_id=None,
        rerank_profile_id=profile_id,
    )
    profile = SimpleNamespace(
        id=profile_id,
        provider="qwen",
        default_model="qwen3.5",
        base_url="https://router.example/v1",
        allowed_tasks=["RERANK"],
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
    monkeypatch.setattr(profiles, "_resolve_api_key", lambda _profile: "sk-rerank")
    monkeypatch.setattr(profiles, "_global_credentials", lambda _provider: (None, None))

    resolved = profiles.resolve_profile_for_task(project_id=project_id, task_type="RERANK")

    assert resolved.profile_id == str(profile_id)
    assert resolved.provider == "qwen"
    assert resolved.model == "qwen3.5"
