from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.api import routes
from app.schemas.contracts import CompletedBidCreateRequest, ProjectModelPolicyUpsertRequest, ProviderProfileCreateRequest


def test_create_provider_profile_api_writes_audit_log(monkeypatch) -> None:
    project_id = str(uuid4())
    profile_id = uuid4()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        routes,
        "create_provider_profile",
        lambda **_kwargs: SimpleNamespace(
            id=profile_id,
            scope_id=uuid4(),
            key_storage=SimpleNamespace(value="ENCRYPTED_DB"),
            provider="qwen",
            default_model="qwen3.5",
        ),
    )
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _provided: "jwt-user")
    monkeypatch.setattr(routes, "record_audit_event", lambda **kwargs: captured.update(kwargs))

    payload = ProviderProfileCreateRequest(
        project_id=project_id,
        provider="qwen",
        base_url="https://example.com/v1",
        default_model="qwen3.5",
        api_key="sk-test",
        key_storage="ENCRYPTED_DB",
        allowed_tasks=["GENERATE"],
    )
    resp = routes.create_provider_profile_api(payload)

    assert resp.profile_id == str(profile_id)
    assert captured["action"] == "provider_profile.create"
    assert captured["actor_user_id"] == "jwt-user"
    assert captured["project_id"] == project_id
    assert captured["target_id"] == str(profile_id)


def test_put_model_policy_api_writes_audit_log(monkeypatch) -> None:
    project_id = str(uuid4())
    captured: dict[str, object] = {}
    policy = SimpleNamespace(
        project_id=uuid4(),
        extract_profile_id=None,
        generate_profile_id=None,
        review_profile_id=None,
        embed_profile_id=None,
        rerank_profile_id=None,
        query_rewrite_profile_id=None,
        program_support_profile_id=None,
        enable_review=True,
        token_budget_total=500000,
        token_budget_used=0,
        concurrency_limits={"generate": 3},
    )

    monkeypatch.setattr(routes, "upsert_project_model_policy", lambda **_kwargs: policy)
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _provided: "jwt-user")
    monkeypatch.setattr(routes, "record_audit_event", lambda **kwargs: captured.update(kwargs))

    resp = routes.put_model_policy_api(project_id, ProjectModelPolicyUpsertRequest(enable_review=True))

    assert resp.project_id == str(policy.project_id)
    assert captured["action"] == "model_policy.upsert"
    assert captured["actor_user_id"] == "jwt-user"
    assert captured["project_id"] == project_id
    assert captured["target_id"] == project_id


def test_create_and_delete_completed_bid_api_write_audit_log(monkeypatch) -> None:
    project_id = str(uuid4())
    record_id = uuid4()
    captured: list[dict[str, object]] = []
    created_at = datetime.now(UTC)

    monkeypatch.setattr(
        routes,
        "create_completed_bid",
        lambda **_kwargs: SimpleNamespace(
            id=record_id,
            project_id=project_id,
            project_name="示例项目",
            engineering_category="市政",
            tenderer="招标人A",
            bid_result="WON",
            file_name="history.pdf",
            file_info=None,
            completed_date=None,
            created_by="jwt-user",
            created_at=created_at,
        ),
    )
    monkeypatch.setattr(routes, "delete_completed_bid", lambda _record_id: True)
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _provided: "jwt-user")
    monkeypatch.setattr(routes, "record_audit_event", lambda **kwargs: captured.append(kwargs))

    create_payload = CompletedBidCreateRequest(
        project_id=project_id,
        project_name="示例项目",
        engineering_category="市政",
        tenderer="招标人A",
        bid_result="WON",
        file_name="history.pdf",
    )
    create_resp = routes.create_completed_bid_api(create_payload)
    delete_resp = routes.delete_completed_bid_api(str(record_id))

    assert create_resp.id == str(record_id)
    assert delete_resp.deleted is True
    assert captured[0]["action"] == "completed_bid.create"
    assert captured[0]["actor_user_id"] == "jwt-user"
    assert captured[0]["project_id"] == project_id
    assert captured[1]["action"] == "completed_bid.delete"
    assert captured[1]["target_id"] == str(record_id)


def test_list_audit_logs_api_maps_rows(monkeypatch) -> None:
    row = SimpleNamespace(
        id=uuid4(),
        project_id=uuid4(),
        actor_user_id="jwt-user",
        action="model_policy.upsert",
        target_id="target-1",
        metadata_json={"changed_fields": ["generate_profile_id"]},
        created_at=datetime.now(UTC),
    )
    monkeypatch.setattr(routes, "list_audit_logs", lambda **_kwargs: [row])

    resp = routes.list_audit_logs_api(project_id=None, action=None, limit=10)

    assert len(resp.items) == 1
    assert resp.items[0].action == "model_policy.upsert"
    assert resp.items[0].actor_user_id == "jwt-user"
    assert resp.items[0].metadata["changed_fields"] == ["generate_profile_id"]
