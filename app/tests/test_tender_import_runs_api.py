from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import routes


def test_list_import_runs_rejects_invalid_project_id() -> None:
    with pytest.raises(HTTPException) as exc:
        routes.list_import_runs(project_id="not-a-uuid", limit=10)
    assert exc.value.status_code == 400
    assert str(exc.value.detail) == "invalid project_id"
