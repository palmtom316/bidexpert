from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects import postgresql


def test_json_type_uses_jsonb_in_postgres() -> None:
    from app.db.types import JSONDictType

    impl = JSONDictType().load_dialect_impl(postgresql.dialect())
    assert isinstance(impl, postgresql.JSONB)


def test_v11_migration_contains_jsonb_gin_and_workflow_columns() -> None:
    migration_dir = Path("migrations/versions")
    candidates = sorted(migration_dir.glob("*_v11_jsonb_gin_and_workflow_fields.py"))
    assert candidates, "expected v11 migration file"

    text = candidates[-1].read_text(encoding="utf-8")
    assert "JSONB" in text
    assert "GIN" in text
    assert "current_step" in text
    assert "step_status" in text
    assert "resume_from_step" in text
    assert "parent_chunk_id" in text
    assert "anchor_type" in text
