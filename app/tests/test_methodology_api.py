from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.api import routes
from app.schemas.contracts import (
    MethodologyExtractRequest,
    MethodologyExtractResponse,
    MethodologyPublishResponse,
    MethodologyReviewRequest,
)


def test_methodology_extract_route(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_create_run(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return "run-001"

    monkeypatch.setattr(routes, "create_methodology_extract_run", _fake_create_run)
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _value: "tester")

    response = routes.methodology_extract(
        MethodologyExtractRequest(
            text="通用进度保障做法",
            source_type="public_doc",
            source_note="公开资料",
            domain="配网",
            tags=["进度", "资源"],
        )
    )

    assert isinstance(response, MethodologyExtractResponse)
    assert response.run_id == "run-001"
    assert response.status == "RECEIVED"
    assert captured["source_type"] == "public_doc"


def test_methodology_extract_upload_route(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_create_from_file(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return "run-upload-001"

    monkeypatch.setattr(routes, "create_methodology_extract_run_from_file", _fake_create_from_file)
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _value: "tester")

    async def _run() -> None:
        file = UploadFile(filename="snippet.md", file=BytesIO(b"# title\\n\\ncontent"))
        response = await routes.methodology_extract_upload(
            file=file,
            source_type="sample",
            source_note="upload-source",
            domain="配网",
            tags="进度,质量",
        )
        assert response.run_id == "run-upload-001"
        assert response.status == "RECEIVED"

    asyncio.run(_run())
    assert captured["filename"] == "snippet.md"
    assert captured["source_type"] == "sample"


def test_methodology_review_then_publish_route(monkeypatch) -> None:
    monkeypatch.setattr(routes, "review_methodology_run", lambda **_kwargs: "approved")
    monkeypatch.setattr(routes, "publish_methodology_run", lambda **_kwargs: "MSNIP-2026-0001")
    monkeypatch.setattr(routes, "_resolved_created_by", lambda _value: "tester")

    review_response = routes.methodology_review(
        "run-001",
        MethodologyReviewRequest(status="approved", comment="ok"),
    )
    assert review_response.status == "approved"

    publish_response = routes.methodology_publish("run-001")
    assert isinstance(publish_response, MethodologyPublishResponse)
    assert publish_response.snippet_id == "MSNIP-2026-0001"
