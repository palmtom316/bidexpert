"""Tests for app.tender.report — import report generation."""
from __future__ import annotations

import json
from pathlib import Path

from app.tender.report import generate_import_report
from app.tender.schemas import StepReport


class TestGenerateImportReport:
    def test_basic_report(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        steps = [
            StepReport(step="parse", status="OK", duration_ms=100),
            StepReport(step="extract", status="OK", duration_ms=200),
        ]
        report = generate_import_report(
            tender_id="t-001",
            filename="test.pdf",
            workspace=workspace,
            step_reports=steps,
            final_status="COMPLETED",
        )
        assert report.tender_id == "t-001"
        assert report.filename == "test.pdf"
        assert report.final_status == "COMPLETED"
        assert len(report.steps) == 2
        assert report.fatal_blocked is False

    def test_writes_json_file(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        generate_import_report(
            tender_id="t-002",
            filename="doc.pdf",
            workspace=workspace,
            step_reports=[],
            final_status="FAILED",
            fatal_blocked=True,
        )
        report_path = workspace / "derived" / "import_report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text(encoding="utf-8"))
        assert data["tender_id"] == "t-002"
        assert data["fatal_blocked"] is True
        assert data["final_status"] == "FAILED"

    def test_derived_files_listed(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        derived = workspace / "derived"
        derived.mkdir(parents=True)
        (derived / "sections.json").write_text("{}")
        (derived / "facts.json").write_text("{}")

        report = generate_import_report(
            tender_id="t-003",
            filename="x.pdf",
            workspace=workspace,
            step_reports=[],
            final_status="OK",
        )
        # derived_files should include the pre-existing files + the report itself
        assert "sections.json" in report.derived_files
        assert "facts.json" in report.derived_files

    def test_no_derived_dir(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        workspace.mkdir()
        # No derived dir exists yet
        generate_import_report(
            tender_id="t-004",
            filename="y.pdf",
            workspace=workspace,
            step_reports=[],
            final_status="OK",
        )
        # Should still succeed — derived dir created by the function
        assert (workspace / "derived" / "import_report.json").exists()
