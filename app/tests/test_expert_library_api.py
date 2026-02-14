from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.api import routes
from app.schemas.contracts import (
    ExpertLibraryChunkItem,
    ExpertLibraryDocItem,
    ExpertLibraryIngestResponse,
    ExpertLibraryStructuredIngestItem,
    ExpertLibraryStructuredIngestRequest,
    ExpertLibraryStructuredIngestResponse,
)


def test_expert_library_docs_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "list_expert_docs",
        lambda **_: [
            ExpertLibraryDocItem(
                expert_doc_id="d1",
                title="doc-1",
                industry_tag="政企",
                doc_type="EXPERT_HISTORY",
                created_at="2026-02-14T00:00:00",
                chunk_count=2,
            )
        ],
    )
    result = routes.expert_library_docs(project_id=None, industry_tag="政企", limit=10)
    assert len(result.items) == 1
    assert result.items[0].chunk_count == 2


def test_expert_library_chunks_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "list_expert_chunks",
        lambda **_: [
            ExpertLibraryChunkItem(
                chunk_id="c1",
                excerpt_text="示例内容",
                section_anchor="第一章",
                quality_score=80.0,
                valid_to=None,
                created_at="2026-02-14T00:00:00",
            )
        ],
    )
    result = routes.expert_library_doc_chunks("doc-uuid", limit=10)
    assert result.expert_doc_id == "doc-uuid"
    assert result.items[0].chunk_id == "c1"


def test_expert_library_ingest_response_schema() -> None:
    payload = ExpertLibraryIngestResponse(
        status="SUCCEEDED",
        expert_doc_id="doc",
        source_document_id="src",
        filename="x.pdf",
        page_count=3,
        chunk_count=5,
        qdrant_upserted=5,
        warnings=[],
    )
    assert payload.status == "SUCCEEDED"


def test_expert_library_structured_ingest_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "ingest_structured_expert_knowledge",
        lambda **_: ExpertLibraryStructuredIngestResponse(
            status="SUCCEEDED",
            total_docs=2,
            total_chunks=4,
            items=[
                ExpertLibraryStructuredIngestItem(
                    category="STANDARD",
                    expert_doc_id="doc-1",
                    title="规范",
                    chunk_count=2,
                    qdrant_upserted=2,
                    warnings=[],
                )
            ],
        ),
    )
    payload = ExpertLibraryStructuredIngestRequest(
        project_id="p1",
        industry_tag="政企",
        created_by="tester",
        standard_items=["应符合国家标准"],
    )
    result = routes.expert_library_ingest_structured(payload)
    assert result.status == "SUCCEEDED"
    assert result.total_docs == 2


def test_expert_library_ingest_upload_route_with_model_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_ingest(**kwargs) -> ExpertLibraryIngestResponse:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return ExpertLibraryIngestResponse(
            status="SUCCEEDED",
            expert_doc_id="doc-x",
            source_document_id="src-x",
            filename="history.pdf",
            page_count=2,
            chunk_count=3,
            qdrant_upserted=3,
            warnings=[],
        )

    monkeypatch.setattr(routes, "ingest_historical_pdf", _fake_ingest)

    async def _run() -> None:
        file = UploadFile(filename="history.pdf", file=BytesIO(b"%PDF-1.4"))
        result = await routes.expert_library_ingest_upload(
            file=file,
            project_id="p-1",
            industry_tag="政企",
            title="历史项目",
            created_by="tester",
            doc_type="EXPERT_HISTORY",
            model_id="gemini-2.5-pro",
        )
        assert result.expert_doc_id == "doc-x"
        assert captured["model_id"] == "gemini-2.5-pro"

    asyncio.run(_run())
