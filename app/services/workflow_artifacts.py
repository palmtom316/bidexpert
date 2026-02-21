from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import settings


def _artifact_dir(outline_id: str, section_key: str) -> Path:
    root = Path(settings.workflow_artifact_dir)
    path = root / str(outline_id) / str(section_key)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _artifact_file(outline_id: str, section_key: str, gate: str) -> Path:
    return _artifact_dir(outline_id=outline_id, section_key=section_key) / f"{gate}.json"


def persist_gate_artifact(*, outline_id: str, section_key: str, gate: str, payload: dict[str, Any]) -> str:
    target = _artifact_file(outline_id=outline_id, section_key=section_key, gate=gate)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(target)


def load_gate_artifact(outline_id: str, section_key: str, gate: str) -> dict[str, Any] | None:
    target = _artifact_file(outline_id=outline_id, section_key=section_key, gate=gate)
    if not target.exists():
        return None
    content = target.read_text(encoding="utf-8")
    loaded = json.loads(content)
    return loaded if isinstance(loaded, dict) else None
