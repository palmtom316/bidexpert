from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Callable

from app.core.config import settings


def parse_scorecard(
    *,
    project_id: str,
    tender_text: str,
    llm_extract_fn: Callable[[str, dict], dict] | None = None,
) -> dict:
    table_blocks = extract_table_blocks(tender_text)
    prompt = _build_structuring_prompt(table_blocks)
    extractor = llm_extract_fn or _default_llm_extract
    structured_json = extractor(
        prompt=prompt,
        response_format={"type": "json_object"},
    )
    scorecard_id = str(uuid.uuid4())
    payload = {
        "scorecard_id": scorecard_id,
        "project_id": project_id,
        "status": "PENDING_CONFIRM",
        "table_blocks": table_blocks,
        "structured_json": structured_json if isinstance(structured_json, dict) else {},
        "locked": False,
    }
    _save_scorecard(payload)
    return {
        "scorecard_id": scorecard_id,
        "status": payload["status"],
        "table_blocks": table_blocks,
        "structured_json": payload["structured_json"],
    }


def confirm_scorecard(*, scorecard_id: str, project_id: str, approved: bool, reviewer: str) -> dict:
    payload = _load_scorecard(scorecard_id)
    if payload.get("project_id") != project_id:
        raise ValueError("scorecard project mismatch")
    if not approved:
        raise ValueError("scorecard requires human confirmation before lock")
    if payload.get("status") == "LOCKED":
        return {"scorecard_id": scorecard_id, "status": "LOCKED", "locked": True}

    payload["status"] = "LOCKED"
    payload["locked"] = True
    payload["reviewer"] = reviewer
    _save_scorecard(payload)
    return {
        "scorecard_id": scorecard_id,
        "status": "LOCKED",
        "locked": True,
    }


def extract_table_blocks(markdown_text: str) -> list[str]:
    lines = markdown_text.splitlines()
    blocks: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if "|" in stripped:
            current.append(stripped)
            continue
        if current:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)

    return ["\n".join(block) for block in blocks if len(block) >= 2]


def _build_structuring_prompt(table_blocks: list[str]) -> str:
    joined = "\n\n".join(table_blocks) if table_blocks else "(no score table blocks found)"
    return (
        "你是评分细则结构化助手。请从评分表中提取 JSON。\n"
        "输出字段：total_score, items[].item_id/name/max_score/criteria。\n\n"
        f"评分表内容：\n{joined}"
    )


def _default_llm_extract(*, prompt: str, response_format: dict) -> dict:  # noqa: ARG001
    # Deterministic fallback parser for tests/offline environments.
    lines = [line.strip() for line in prompt.splitlines() if line.strip().startswith("|")]
    items: list[dict] = []
    for idx, line in enumerate(lines[2:], start=1):
        columns = [cell.strip() for cell in line.strip("|").split("|")]
        if len(columns) < 2:
            continue
        name = columns[0]
        score_value = _parse_score(columns[1])
        items.append(
            {
                "item_id": f"S-{idx:03d}",
                "name": name,
                "max_score": score_value,
                "criteria": [],
            }
        )
    total_score = sum(float(item["max_score"]) for item in items)
    return {"total_score": total_score, "items": items}


def _parse_score(raw: str) -> float:
    digits = []
    for ch in raw:
        if ch.isdigit() or ch == ".":
            digits.append(ch)
    try:
        return float("".join(digits)) if digits else 0.0
    except ValueError:
        return 0.0


def _scorecard_store_dir() -> Path:
    store_dir = Path(settings.tender_workspace_dir) / "scorecards"
    store_dir.mkdir(parents=True, exist_ok=True)
    return store_dir


def _scorecard_path(scorecard_id: str) -> Path:
    return _scorecard_store_dir() / f"{scorecard_id}.json"


def _save_scorecard(payload: dict) -> None:
    scorecard_id = str(payload.get("scorecard_id", "")).strip()
    if not scorecard_id:
        raise ValueError("scorecard_id is required")
    path = _scorecard_path(scorecard_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_scorecard(scorecard_id: str) -> dict:
    path = _scorecard_path(scorecard_id)
    if not path.is_file():
        raise ValueError("scorecard not found")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("scorecard state is corrupted") from exc
    if not isinstance(payload, dict):
        raise ValueError("scorecard state is corrupted")
    return payload
