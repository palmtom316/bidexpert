from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import AuditLog, ExpertDoc, LLMCallLog
from app.services.embedding import embed_text
from app.services.adapters import GenerationResult
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.qdrant_store import RetrievedEvidence


def test_sqlite_schema_supports_uuid_and_array_like_fields() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    with Session() as db:
        expert = ExpertDoc(
            doc_type="EXPERT_HISTORY",
            created_by="tester",
            forbidden_tags=["PRICING_RELATED"],
        )
        log = LLMCallLog(
            actor_user_id="tester",
            model_name="gpt-5",
            purpose="SECTION_GENERATE",
            evidence_ids=[uuid.uuid4(), uuid.uuid4()],
        )
        db.add(expert)
        db.add(log)
        db.commit()

        saved_expert = db.get(ExpertDoc, expert.id)
        saved_log = db.get(LLMCallLog, log.id)

    assert saved_expert is not None
    assert saved_expert.forbidden_tags == ["PRICING_RELATED"]
    assert saved_log is not None
    assert len(saved_log.evidence_ids) == 2
    assert isinstance(saved_log.evidence_ids[0], uuid.UUID)


def test_generation_rejects_nonexistent_evidence_ids_in_payload(monkeypatch) -> None:
    monkeypatch.setattr("app.services.generation_pipeline.decompose_requirement", lambda _: ["sub-1"])
    monkeypatch.setattr(
        "app.services.generation_pipeline.retrieve_for_subrequirements",
        lambda **_: {"sub-1": []},
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.merge_retrieval",
        lambda _: (
            ["e-1"],
            {"sub-1": ["e-1"]},
            [RetrievedEvidence(chunk_id="e-1", score=0.9, text="公司具备类似业绩。", payload={})],
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.run_three_gates",
        lambda **_: SimpleNamespace(status="SUPPORTED", missing_sentences=[], coverage=1.0),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.reserve_budget_persistent",
        lambda **_: (True, 1000),
    )
    monkeypatch.setattr("app.services.generation_pipeline.get_cache", lambda *_: None)
    monkeypatch.setattr("app.services.generation_pipeline.set_cache", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.generation_pipeline.log_llm_call", lambda **_: None)
    monkeypatch.setattr(
        "app.services.generation_pipeline.resolve_profile_for_task",
        lambda **_: SimpleNamespace(profile_id=None, provider="qwen", model="qwen3", api_key=None, base_url=None),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.resolve_profile_chain_for_task",
        lambda **_: [SimpleNamespace(profile_id=None, provider="qwen", model="qwen3", api_key=None, base_url=None)],
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.get_project_model_policy",
        lambda *_: SimpleNamespace(enable_review=False),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.generate_with_fallback_chain",
        lambda **_: (
            GenerationResult(
                text="",
                provider="qwen",
                model="qwen3",
                content_json={
                    "content_blocks": [
                        {
                            "type": "paragraph",
                            "text": "我们完全满足要求。",
                            "evidence_ids": ["fake-evidence-id"],
                        }
                    ]
                },
            ),
            0,
        ),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-SEC-1",
        requirement_text="必须提供近三年同类项目业绩。",
        project_id=str(uuid.uuid4()),
    )

    assert result.status == "NEED_HUMAN_INPUT"
    assert result.generated_text == "NEED_HUMAN_INPUT"
    assert "generate_evidence_binding_invalid" in result.warnings


def test_default_cors_is_allowlist_not_wildcard() -> None:
    assert Settings().cors_origins != "*"


def test_embedding_mock_fallback_is_blocked_in_prod_without_credentials(monkeypatch) -> None:
    from app.services import embedding

    monkeypatch.setattr(embedding.settings, "app_env", "prod", raising=False)

    with pytest.raises(RuntimeError, match="No embedding API credentials configured"):
        embed_text("missing credential", vector_size=8)


def test_runtime_baseline_rejects_production_alias(monkeypatch) -> None:
    from app.core import config

    monkeypatch.setattr(config.settings, "app_env", "production", raising=False)

    with pytest.raises(RuntimeError, match="BIDEXPERT_APP_ENV=prod"):
        config.validate_runtime_baseline()


def test_audit_log_schema_roundtrip() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine)
    with Session() as db:
        row = AuditLog(
            actor_user_id="auditor",
            action="model_policy.upsert",
            target_id="project-1",
            metadata_json={"changed_fields": ["generate_profile_id"]},
        )
        db.add(row)
        db.commit()
        saved = db.get(AuditLog, row.id)

    assert saved is not None
    assert saved.actor_user_id == "auditor"
    assert saved.action == "model_policy.upsert"
    assert saved.metadata_json["changed_fields"] == ["generate_profile_id"]
