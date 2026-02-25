from __future__ import annotations

import logging

from app.worker import tasks


def test_safe_update_run_progress_logs_warning_for_missing_outline(monkeypatch, caplog) -> None:
    def _raise_value_error(**kwargs):  # noqa: ANN003
        del kwargs
        raise ValueError("outline not found")

    monkeypatch.setattr(tasks, "update_run_progress", _raise_value_error)

    with caplog.at_level(logging.WARNING):
        tasks._safe_update_run_progress(
            outline_id="missing-outline",
            current_step="G2",
            step_status="failed",
            resume_from_step="G2",
        )

    assert "outline not found" in caplog.text
