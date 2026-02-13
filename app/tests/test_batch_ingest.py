from __future__ import annotations

from pathlib import Path

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

    payload = BatchIngestDirectoryRequest(directory=str(tmp_path))
    result = routes.enqueue_ingest_directory(payload)

    assert result.status == "PENDING"
    assert result.total_files == 2
    assert len(result.task_ids) == 2
    assert all(item.lower().endswith(".pdf") for item in seen)
