from __future__ import annotations

import sqlite3
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


def test_initial_migration_does_not_reference_unbound_text_symbol() -> None:
    migration_path = Path("migrations/versions/47ace6ac701b_add_reviewreport_and_scoringreport.py")
    assert migration_path.exists(), "expected initial migration file"
    text = migration_path.read_text(encoding="utf-8")
    assert "ARRAY(Text())" not in text


def _sqlite_column_types(db_path: Path, table: str) -> dict[str, str]:
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]): str(row[2]).upper() for row in rows}


def _sqlite_foreign_keys(db_path: Path, table: str) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        return list(conn.execute(f"PRAGMA foreign_key_list({table})").fetchall())


def test_review_report_project_id_is_uuid_foreign_key_after_migrations() -> None:
    db_path = Path("bidexpert.db")
    assert db_path.exists(), "expected sqlite database at project root"

    columns = _sqlite_column_types(db_path, "review_report")
    assert columns.get("project_id") == "UUID"

    foreign_keys = _sqlite_foreign_keys(db_path, "review_report")
    assert any(row[3] == "project_id" and row[2] == "project" and row[4] == "id" for row in foreign_keys)


def test_scoring_report_project_id_is_uuid_foreign_key_after_migrations() -> None:
    db_path = Path("bidexpert.db")
    assert db_path.exists(), "expected sqlite database at project root"

    columns = _sqlite_column_types(db_path, "scoring_report")
    assert columns.get("project_id") == "UUID"

    foreign_keys = _sqlite_foreign_keys(db_path, "scoring_report")
    assert any(row[3] == "project_id" and row[2] == "project" and row[4] == "id" for row in foreign_keys)


def test_completed_bid_project_id_is_uuid_foreign_key_after_migrations() -> None:
    db_path = Path("bidexpert.db")
    assert db_path.exists(), "expected sqlite database at project root"

    columns = _sqlite_column_types(db_path, "completed_bid")
    assert columns.get("project_id") == "UUID"

    foreign_keys = _sqlite_foreign_keys(db_path, "completed_bid")
    assert any(row[3] == "project_id" and row[2] == "project" and row[4] == "id" for row in foreign_keys)
