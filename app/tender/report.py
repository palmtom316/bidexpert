"""Import report generation — summarize pipeline execution."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.tender.schemas import ImportReport, StepReport

logger = logging.getLogger(__name__)


def generate_import_report(
    *,
    tender_id: str,
    filename: str,
    workspace: Path,
    step_reports: list[StepReport],
    final_status: str,
    fatal_blocked: bool = False,
) -> ImportReport:
    """Generate the final import report summarizing all pipeline steps."""
    derived_dir = workspace / "derived"
    derived_files = sorted(f.name for f in derived_dir.iterdir() if f.is_file()) if derived_dir.is_dir() else []

    report = ImportReport(
        tender_id=tender_id,
        filename=filename,
        steps=step_reports,
        final_status=final_status,
        fatal_blocked=fatal_blocked,
        derived_files=derived_files,
    )

    # Save to derived directory
    derived_dir.mkdir(parents=True, exist_ok=True)
    report_path = derived_dir / "import_report.json"
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    logger.info(
        "import report: tender=%s, status=%s, %d steps, %d derived files",
        tender_id, final_status, len(step_reports), len(derived_files),
    )
    return report
