from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
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


def test_expert_library_structured_ingest_route_accepts_extended_categories(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_ingest(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return ExpertLibraryStructuredIngestResponse(
            status="SUCCEEDED",
            total_docs=1,
            total_chunks=1,
            items=[
                ExpertLibraryStructuredIngestItem(
                    category="SAFETY_PRODUCTION",
                    expert_doc_id="doc-2",
                    title="安全生产",
                    chunk_count=1,
                    qdrant_upserted=1,
                    warnings=[],
                )
            ],
        )

    monkeypatch.setattr(routes, "ingest_structured_expert_knowledge", _fake_ingest)
    payload = ExpertLibraryStructuredIngestRequest(
        project_id="p1",
        industry_tag="政企",
        created_by="tester",
        safety_production_items=["三级安全教育记录完整"],
        quality_management_items=["质量管理体系证书在有效期内"],
        equipment_capability_items=["关键机械设备清单齐全"],
        financial_credit_items=["近三年财务审计报告完整"],
        award_honors_items=["获得省级优质工程奖"],
        service_commitment_items=["提供 7x24 现场响应"],
    )
    result = routes.expert_library_ingest_structured(payload)

    assert result.status == "SUCCEEDED"
    assert captured["safety_production_items"] == ["三级安全教育记录完整"]
    assert captured["quality_management_items"] == ["质量管理体系证书在有效期内"]
    assert captured["equipment_capability_items"] == ["关键机械设备清单齐全"]
    assert captured["financial_credit_items"] == ["近三年财务审计报告完整"]
    assert captured["award_honors_items"] == ["获得省级优质工程奖"]
    assert captured["service_commitment_items"] == ["提供 7x24 现场响应"]


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
            ocr_provider="docai",
            ocr_api_key="ocr-key-1",
            ocr_base_url="https://ocr.example/v1",
            ocr_model="glm-ocr",
        )
        assert result.expert_doc_id == "doc-x"
        assert captured["model_id"] == "gemini-2.5-pro"
        assert captured["ocr_provider"] == "docai"
        assert captured["ocr_api_key"] == "ocr-key-1"
        assert captured["ocr_base_url"] == "https://ocr.example/v1"
        assert captured["ocr_model"] == "glm-ocr"

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
    seen_providers: list[str | None] = []
    seen_ocr_api_keys: list[str | None] = []

    def _fake_ingest(**kwargs) -> ExpertLibraryIngestResponse:  # type: ignore[no-untyped-def]
        filename = str(kwargs.get("filename") or "")
        seen_providers.append(kwargs.get("ocr_provider"))
        seen_ocr_api_keys.append(kwargs.get("ocr_api_key"))
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
            ocr_provider="tesseract",
            ocr_api_key="ocr-key-batch",
            ocr_base_url="https://ocr-batch.example/v1",
            ocr_model="glm-ocr",
        )
        assert result.total_files == 2
        assert result.success_count == 1
        assert result.failure_count == 1
        assert result.status == "PARTIAL_SUCCESS"
        assert result.items[0].status == "SUCCEEDED"
        assert result.items[1].status == "FAILED"
        assert "docx" in (result.items[1].error or "")
        assert seen_providers == ["tesseract", "tesseract"]
        assert seen_ocr_api_keys == ["ocr-key-batch", "ocr-key-batch"]

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
            ocr_provider="hunyuan",
            ocr_api_key="ocr-key-2",
            ocr_base_url="https://ocr2.example/v1",
            ocr_model="glm-ocr",
        )
        assert result.conversion_id == "conv-001"
        assert captured["filename"] == "history.docx"
        assert captured["ocr_provider"] == "hunyuan"
        assert captured["ocr_api_key"] == "ocr-key-2"
        assert captured["ocr_base_url"] == "https://ocr2.example/v1"
        assert captured["ocr_model"] == "glm-ocr"

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


def test_confirm_conversion_rejects_path_traversal_conversion_id(monkeypatch) -> None:
    from app.services import expert_library

    monkeypatch.setattr(expert_library.settings, "expert_library_root", "data/tender-expert-lib")

    with pytest.raises(ValueError, match="invalid conversion_id"):
        expert_library.confirm_structured_conversion_ingest(
            conversion_id="../escape",
            project_id=None,
            industry_tag=None,
            title=None,
            created_by="tester",
            doc_type="EXPERT_HISTORY",
            model_id=None,
        )
