from __future__ import annotations

from pathlib import Path


def test_methodology_migration_file_exists() -> None:
    migration_dir = Path("migrations/versions")
    candidates = sorted(migration_dir.glob("*_add_methodology_runs_and_snippets.py"))
    assert candidates, "expected methodology migration file"


def test_methodology_migration_contains_required_schema() -> None:
    migration_dir = Path("migrations/versions")
    candidates = sorted(migration_dir.glob("*_add_methodology_runs_and_snippets.py"))
    assert candidates, "expected methodology migration file"

    text = candidates[-1].read_text(encoding="utf-8")
    assert "methodology_run" in text
    assert "methodology_snippet" in text
    assert "review_status" in text
    assert "risk_level" in text
    assert "similarity_score" in text
