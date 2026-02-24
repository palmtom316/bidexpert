"""Task 1: 生产基线与已知阻断缺陷修复 — RED tests.

Covers:
- R18: validate_runtime_baseline() must check master_key_b64 and model validity in prod
- R26a: DraftGenerationResponse defaults must match registry GENERATE chain head
- R26b: CompletedBid.project_id must be UUID FK to project.id
- R26c: langextract_default_model must exist in registry
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, inspect as sa_inspect
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.db.base import Base
from app.models import tables  # noqa: F401  — register all models
from app.models.tables import CompletedBid, Project


# ---------------------------------------------------------------------------
# R18: validate_runtime_baseline — master_key and model checks in prod
# ---------------------------------------------------------------------------

def test_baseline_rejects_prod_without_master_key(monkeypatch) -> None:
    """prod env without master_key_b64 must raise RuntimeError."""
    from app.core import config

    monkeypatch.setattr(config.settings, "app_env", "prod", raising=False)
    monkeypatch.setattr(config.settings, "master_key_b64", None, raising=False)
    # satisfy other existing prod checks
    monkeypatch.setattr(config.settings, "vault_redis_fallback_enabled", False, raising=False)
    monkeypatch.setattr(config.settings, "cors_origins", "https://app.example.com", raising=False)
    monkeypatch.setattr(config.settings, "database_url", "postgresql://u:p@db/bidexpert", raising=False)
    monkeypatch.setattr(config.settings, "redis_url", "redis://:secret@redis:6379/0", raising=False)

    with pytest.raises(RuntimeError, match="master_key"):
        config.validate_runtime_baseline()


def test_baseline_rejects_prod_with_unregistered_default_model(monkeypatch) -> None:
    """prod env where langextract_default_model is not in registry must raise."""
    from app.core import config

    monkeypatch.setattr(config.settings, "app_env", "prod", raising=False)
    monkeypatch.setattr(config.settings, "master_key_b64", "dGVzdA==", raising=False)
    monkeypatch.setattr(config.settings, "langextract_default_model", "nonexistent-model-xyz", raising=False)
    monkeypatch.setattr(config.settings, "vault_redis_fallback_enabled", False, raising=False)
    monkeypatch.setattr(config.settings, "cors_origins", "https://app.example.com", raising=False)
    monkeypatch.setattr(config.settings, "database_url", "postgresql://u:p@db/bidexpert", raising=False)
    monkeypatch.setattr(config.settings, "redis_url", "redis://:secret@redis:6379/0", raising=False)

    with pytest.raises(RuntimeError, match="langextract_default_model"):
        config.validate_runtime_baseline()


# ---------------------------------------------------------------------------
# R26a: DraftGenerationResponse defaults must match registry GENERATE head
# ---------------------------------------------------------------------------

def test_draft_generation_response_defaults_match_registry() -> None:
    """Default llm_provider/llm_model on DraftGenerationResponse must be the
    first entry in the registry GENERATE fallback chain."""
    from app.llm.model_registry import default_model_for_role
    from app.schemas.contracts import DraftGenerationResponse

    expected_provider, expected_model = default_model_for_role("GENERATE")

    defaults = DraftGenerationResponse(
        generated_text="x",
        evidence_ids=[],
        status="ok",
        missing_sentences=[],
        coverage=1.0,
    )
    assert defaults.llm_provider == expected_provider, (
        f"expected default provider={expected_provider!r}, got {defaults.llm_provider!r}"
    )
    assert defaults.llm_model == expected_model, (
        f"expected default model={expected_model!r}, got {defaults.llm_model!r}"
    )


# ---------------------------------------------------------------------------
# R26b: CompletedBid.project_id must be UUID FK → project.id
# ---------------------------------------------------------------------------

def test_completed_bid_project_id_is_uuid_fk() -> None:
    """CompletedBid.project_id column must be GUID/UUID with FK to project.id."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    inspector = sa_inspect(engine)
    columns = {col["name"]: col for col in inspector.get_columns("completed_bid")}
    assert "project_id" in columns

    fks = inspector.get_foreign_keys("completed_bid")
    fk_cols = {fk["constrained_columns"][0]: fk for fk in fks if fk["constrained_columns"]}
    assert "project_id" in fk_cols, "completed_bid.project_id must have a foreign key"
    assert fk_cols["project_id"]["referred_table"] == "project"
    assert fk_cols["project_id"]["referred_columns"] == ["id"]


def test_completed_bid_project_id_roundtrip_with_uuid() -> None:
    """CompletedBid.project_id must accept UUID values and round-trip correctly."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        project = Project(name="Test", owner_user_id="tester")
        db.add(project)
        db.flush()

        bid = CompletedBid(
            project_id=project.id,
            project_name="Test Bid",
            file_name="test.pdf",
            created_by="tester",
        )
        db.add(bid)
        db.commit()

        saved = db.get(CompletedBid, bid.id)
        assert saved is not None
        assert saved.project_id == project.id
        assert isinstance(saved.project_id, uuid.UUID)


# ---------------------------------------------------------------------------
# R26c: langextract_default_model must exist in registry
# ---------------------------------------------------------------------------

def test_langextract_default_model_exists_in_registry() -> None:
    """The configured langextract_default_model must be a registered model."""
    from app.core.config import settings
    from app.llm.model_registry import get_registry_entry

    model_name = settings.langextract_default_model
    # model_name could be "provider:model" or just "model"
    if ":" in model_name:
        provider, model = model_name.split(":", maxsplit=1)
    else:
        # search all entries
        provider = None
        model = model_name

    if provider:
        entry = get_registry_entry(provider, model)
    else:
        from app.llm.model_registry import list_registry_entries
        entry = next(
            (e for e in list_registry_entries() if e.model_name == model),
            None,
        )

    assert entry is not None, (
        f"langextract_default_model={model_name!r} not found in model registry"
    )
