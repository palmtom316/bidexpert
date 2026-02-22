from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import BatchIngestDirectoryRequest


def test_enqueue_ingest_directory_filters_pdf_and_enqueues(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "b.PDF").write_bytes(b"%PDF-1.4")
    (tmp_path / "readme.txt").write_text("noop", encoding="utf-8")

    seen: list[str] = []

    class _Task:
        @staticmethod
        def delay(file_path: str) -> object:
            seen.append(file_path)
            return type("R", (), {"id": f"task-{len(seen)}"})()

    monkeypatch.setattr(routes, "ingest_document_task", _Task)
    monkeypatch.setattr(routes.settings, "upload_dir", str(tmp_path), raising=False)

    payload = BatchIngestDirectoryRequest(directory=str(tmp_path))
    result = routes.enqueue_ingest_directory(payload)

    assert result.status == "PENDING"
    assert result.total_files == 2
    assert len(result.task_ids) == 2
    assert all(item.lower().endswith(".pdf") for item in seen)


def test_enqueue_ingest_directory_rejects_path_outside_upload_dir(monkeypatch, tmp_path: Path) -> None:
    upload_root = tmp_path / "upload-root"
    upload_root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "a.pdf").write_bytes(b"%PDF-1.4")

    class _Task:
        @staticmethod
        def delay(file_path: str) -> object:  # noqa: ARG004
            return type("R", (), {"id": "task-1"})()

    monkeypatch.setattr(routes, "ingest_document_task", _Task)
    monkeypatch.setattr(routes.settings, "upload_dir", str(upload_root), raising=False)

    with pytest.raises(HTTPException) as exc_info:
        routes.enqueue_ingest_directory(BatchIngestDirectoryRequest(directory=str(outside)))
    assert exc_info.value.status_code == 400


def test_ingest_document_task_enables_autoretry_backoff() -> None:
    task_obj = routes.ingest_document_task
    autoretry_for = tuple(getattr(task_obj, "autoretry_for", ()) or ())

    assert RuntimeError in autoretry_for
    assert OSError in autoretry_for
    assert bool(getattr(task_obj, "retry_backoff", False)) is True
    assert int(getattr(task_obj, "retry_backoff_max", 0)) > 0
    assert bool(getattr(task_obj, "retry_jitter", False)) is True
