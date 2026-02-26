from __future__ import annotations

import pytest

from app.services import scorecard_parser


def test_scorecard_parser_extracts_table_blocks_then_structures_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scorecard_parser.settings, "tender_workspace_dir", str(tmp_path), raising=False)
    markdown = """
## 评分办法

| 评分项 | 分值 | 说明 |
| --- | --- | --- |
| 项目经理业绩 | 10 | 提供类似项目证明 |
| 施工组织设计 | 20 | 方案完整可执行 |
"""
    result = scorecard_parser.parse_scorecard(
        project_id="proj-1",
        tender_text=markdown,
    )

    assert result["status"] == "PENDING_CONFIRM"
    assert len(result["table_blocks"]) == 1
    assert result["structured_json"]["items"]


def test_scorecard_parser_uses_response_format_json_object(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scorecard_parser.settings, "tender_workspace_dir", str(tmp_path), raising=False)
    captured: dict[str, object] = {}

    def _fake_llm_extract(*, prompt: str, response_format: dict) -> dict:
        captured["prompt"] = prompt
        captured["response_format"] = response_format
        return {
            "total_score": 100,
            "items": [{"item_id": "S-001", "name": "技术", "max_score": 40, "criteria": []}],
        }

    scorecard_parser.parse_scorecard(
        project_id="proj-2",
        tender_text="|评分项|分值|\\n|---|---|\\n|技术|40|",
        llm_extract_fn=_fake_llm_extract,
    )

    assert captured["response_format"] == {"type": "json_object"}


def test_scorecard_requires_human_confirm_before_lock(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scorecard_parser.settings, "tender_workspace_dir", str(tmp_path), raising=False)
    parsed = scorecard_parser.parse_scorecard(
        project_id="proj-3",
        tender_text="|评分项|分值|\\n|---|---|\\n|商务|20|",
    )
    scorecard_id = parsed["scorecard_id"]

    with pytest.raises(ValueError):
        scorecard_parser.confirm_scorecard(
            scorecard_id=scorecard_id,
            project_id="proj-3",
            approved=False,
            reviewer="auditor-1",
        )

    confirmed = scorecard_parser.confirm_scorecard(
        scorecard_id=scorecard_id,
        project_id="proj-3",
        approved=True,
        reviewer="auditor-1",
    )
    assert confirmed["status"] == "LOCKED"
    assert confirmed["locked"] is True


def test_scorecard_confirm_rejects_project_mismatch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(scorecard_parser.settings, "tender_workspace_dir", str(tmp_path), raising=False)
    parsed = scorecard_parser.parse_scorecard(
        project_id="proj-a",
        tender_text="|评分项|分值|\\n|---|---|\\n|商务|20|",
    )

    with pytest.raises(ValueError):
        scorecard_parser.confirm_scorecard(
            scorecard_id=parsed["scorecard_id"],
            project_id="proj-b",
            approved=True,
            reviewer="auditor-2",
        )
