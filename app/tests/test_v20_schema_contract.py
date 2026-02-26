from __future__ import annotations

from pathlib import Path


def _column_names(model: type) -> set[str]:
    return {c.name for c in model.__table__.columns}


def test_v20_schema_entities_and_fields_exist() -> None:
    from app.models import tables

    required = {
        "TenderAddendum": {"parsed_overrides_json"},
        "MandatoryClause": set(),
        "BidAssetPool": {"ownership_role"},
        "ChapterEvidenceLink": set(),
        "GenerationRun": {"current_step", "step_status", "retry_count", "resume_from_step"},
        "ScoreEvaluation": set(),
        "ComplianceReport": set(),
    }

    for model_name, expected_columns in required.items():
        model = getattr(tables, model_name, None)
        assert model is not None, f"missing model: {model_name}"

        columns = _column_names(model)
        for col in expected_columns:
            assert col in columns, f"missing column: {model_name}.{col}"


def test_v20_migration_contract_exists() -> None:
    migration_dir = Path("migrations/versions")
    candidates = sorted(migration_dir.glob("*_add_v20_redline_scorecard_generation_tables.py"))
    assert candidates, "expected v2.0 migration file"

    text = candidates[-1].read_text(encoding="utf-8")
    assert "op.create_table(" in text
    assert '"tender_addendum"' in text
    assert "parsed_overrides_json" in text
    assert '"mandatory_clause"' in text
    assert '"bid_asset_pool"' in text
    assert "ownership_role" in text
    assert '"chapter_evidence_link"' in text
    assert '"generation_run"' in text
    assert "current_step" in text
    assert "step_status" in text
    assert "retry_count" in text
    assert "resume_from_step" in text
    assert '"score_evaluation"' in text
    assert '"compliance_report"' in text
