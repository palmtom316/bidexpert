from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.endpoints import tender


def test_resolve_derived_file_path_rejects_workspace_outside_root(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    outside_workspace = tmp_path / "outside"
    outside_workspace.mkdir()

    monkeypatch.setattr(tender.settings, "tender_workspace_dir", str(workspace_root), raising=False)

    with pytest.raises(HTTPException) as exc:
        tender._resolve_derived_file_path(str(outside_workspace), "import_report.json")

    assert exc.value.status_code == 400
    assert "workspace path is outside configured root" in str(exc.value.detail)


def test_resolve_derived_file_path_rejects_traversal_filename(tmp_path, monkeypatch) -> None:
    workspace_root = tmp_path / "workspaces"
    workspace_root.mkdir()
    workspace = workspace_root / "run-1"
    derived = workspace / "derived"
    derived.mkdir(parents=True)

    monkeypatch.setattr(tender.settings, "tender_workspace_dir", str(workspace_root), raising=False)

    with pytest.raises(HTTPException) as exc:
        tender._resolve_derived_file_path(str(workspace), "../escape.json")

    assert exc.value.status_code == 400
    assert "derived file path escaped workspace boundary" in str(exc.value.detail)
