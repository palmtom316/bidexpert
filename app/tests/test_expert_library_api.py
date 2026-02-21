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


def test_expert_library_ingest_upload_route_accepts_markdown(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_ingest(**kwargs) -> ExpertLibraryIngestResponse:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return ExpertLibraryIngestResponse(
            status="SUCCEEDED",
            expert_doc_id="doc-md",
            source_document_id="src-md",
            filename="history.md",
            page_count=1,
            chunk_count=2,
            qdrant_upserted=2,
            warnings=[],
        )

    monkeypatch.setattr(routes, "ingest_historical_pdf", _fake_ingest)

    async def _run() -> None:
        file = UploadFile(filename="history.md", file=BytesIO(b"# title\n\nmarkdown content"))
        result = await routes.expert_library_ingest_upload(
            file=file,
            project_id="p-1",
            industry_tag="政企",
            title="markdown-历史项目",
            created_by="tester",
            doc_type="EXPERT_HISTORY",
            model_id="gemini-2.5-pro",
        )
        assert result.expert_doc_id == "doc-md"
        assert captured["filename"] == "history.md"

    asyncio.run(_run())


def test_expert_library_ingest_uploads_route_partial_success(monkeypatch) -> None:
    def _fake_ingest(**kwargs) -> ExpertLibraryIngestResponse:  # type: ignore[no-untyped-def]
        filename = str(kwargs.get("filename") or "")
        if filename.lower().endswith(".doc"):
            raise ValueError("暂不支持 .doc，请另存为 .docx 后上传")
        return ExpertLibraryIngestResponse(
            status="SUCCEEDED",
            expert_doc_id=f"doc-{filename}",
            source_document_id=f"src-{filename}",
            filename=filename,
            page_count=1,
            chunk_count=2,
            qdrant_upserted=2,
            warnings=[],
        )

    monkeypatch.setattr(routes, "ingest_historical_pdf", _fake_ingest)

    async def _run() -> None:
        files = [
            UploadFile(filename="history-a.pdf", file=BytesIO(b"%PDF-1.4")),
            UploadFile(filename="history-b.doc", file=BytesIO(b"legacy word")),
        ]
        result = await routes.expert_library_ingest_uploads(
            files=files,
            project_id="p-1",
            industry_tag="政企",
            title=None,
            created_by="tester",
            doc_type="EXPERT_HISTORY",
            model_id=None,
        )
        assert result.total_files == 2
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.status == "PARTIAL_SUCCESS"
        assert result.items[0].status == "SUCCEEDED"
        assert result.items[1].status == "FAILED"
        assert "docx" in (result.items[1].error or "")

    asyncio.run(_run())


def test_expert_library_convert_upload_route(monkeypatch) -> None:
    from app.schemas.contracts import ExpertLibraryConvertResponse

    captured: dict[str, object] = {}

    def _fake_convert(**kwargs) -> ExpertLibraryConvertResponse:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return ExpertLibraryConvertResponse(
            status="SUCCEEDED",
            conversion_id="conv-001",
            filename="history.docx",
            page_count=1,
            block_count=4,
            section_count=2,
            chunk_count=2,
            preview_sections=["第一章 总则", "第二章 资质"],
            warnings=[],
        )

    monkeypatch.setattr(routes, "convert_upload_to_structured", _fake_convert)

    async def _run() -> None:
        file = UploadFile(
            filename="history.docx",
            file=BytesIO(
                b"PK\x03\x04\x14\x00\x00\x00\x08\x00fake-docx"  # docx-like payload for route plumbing
            ),
        )
        result = await routes.expert_library_convert_upload(
            file=file,
            project_id="p-1",
            industry_tag="政企",
            title="历史项目",
            created_by="tester",
            doc_type="EXPERT_HISTORY",
            model_id=None,
        )
        assert result.conversion_id == "conv-001"
        assert captured["filename"] == "history.docx"

    asyncio.run(_run())


def test_expert_library_convert_confirm_route(monkeypatch) -> None:
    from app.schemas.contracts import ExpertLibraryConvertConfirmRequest

    captured: dict[str, object] = {}

    def _fake_confirm(**kwargs) -> ExpertLibraryIngestResponse:  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return ExpertLibraryIngestResponse(
            status="SUCCEEDED",
            expert_doc_id="doc-confirmed",
            source_document_id="src-confirmed",
            filename="history.docx",
            page_count=1,
            chunk_count=3,
            qdrant_upserted=3,
            warnings=[],
        )

    monkeypatch.setattr(routes, "confirm_structured_conversion_ingest", _fake_confirm)

    payload = ExpertLibraryConvertConfirmRequest(
        conversion_id="conv-001",
        project_id="p-1",
        industry_tag="政企",
        title="历史项目",
        created_by="tester",
        doc_type="EXPERT_HISTORY",
    )
    result = routes.expert_library_convert_confirm(payload)

    assert result.expert_doc_id == "doc-confirmed"
    assert captured["conversion_id"] == "conv-001"
