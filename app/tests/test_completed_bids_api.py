from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import CompletedBidCreateRequest


def _mock_record() -> object:
    return type(
        "Record",
        (),
        {
            "id": uuid.UUID("11111111-1111-1111-1111-111111111111"),
            "project_id": "22222222-2222-2222-2222-222222222222",
            "project_name": "光伏建设项目",
            "engineering_category": "新能源工程",
            "tenderer": "中国移动",
            "bid_result": "WON",
            "file_name": "光伏建设项目_投标文件.docx",
            "file_info": "最终交付版",
            "completed_date": date(2026, 2, 15),
            "created_by": "tester",
            "created_at": datetime(2026, 2, 15, 8, 0, 0, tzinfo=UTC),
        },
    )()


def test_create_completed_bid_route(monkeypatch) -> None:
    monkeypatch.setattr(routes, "create_completed_bid", lambda **_: _mock_record())
    payload = CompletedBidCreateRequest(
        project_id="22222222-2222-2222-2222-222222222222",
        project_name="光伏建设项目",
        engineering_category="新能源工程",
        tenderer="中国移动",
        bid_result="WON",
        file_name="光伏建设项目_投标文件.docx",
        file_info="最终交付版",
        completed_date="2026-02-15",
        created_by="tester",
    )
    result = routes.create_completed_bid_api(payload)
    assert result.project_name == "光伏建设项目"
    assert result.bid_result == "WON"
    assert result.completed_date == "2026-02-15"


def test_list_completed_bids_route(monkeypatch) -> None:
    monkeypatch.setattr(routes, "list_completed_bids", lambda **_: [_mock_record()])
    result = routes.list_completed_bids_api(project_id=None, limit=10)
    assert len(result.items) == 1
    assert result.items[0].file_name.endswith(".docx")


def test_delete_completed_bids_route(monkeypatch) -> None:
    monkeypatch.setattr(routes, "delete_completed_bid", lambda _: True)
    result = routes.delete_completed_bid_api("11111111-1111-1111-1111-111111111111")
    assert result.deleted is True


def test_delete_completed_bids_route_not_found(monkeypatch) -> None:
    monkeypatch.setattr(routes, "delete_completed_bid", lambda _: False)
    try:
        routes.delete_completed_bid_api("11111111-1111-1111-1111-111111111111")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected HTTPException")
