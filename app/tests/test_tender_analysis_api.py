from __future__ import annotations

import asyncio
from io import BytesIO

from fastapi import UploadFile

from app.api import routes
from app.schemas.contracts import (
    TenderAnalysisDetailResponse,
    TenderAnalysisRunItem,
    TenderAnalysisSummary,
    TenderKeyInfoItem,
)


def test_list_tender_analysis_runs_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "list_tender_analysis_runs",
        lambda **_: [
            TenderAnalysisRunItem(
                run_id="r-1",
                project_id="p-1",
                document_id="d-1",
                filename="招标文件.pdf",
                status="SUCCEEDED",
                created_at="2026-02-14T00:00:00",
            )
        ],
    )
    result = routes.list_tender_analysis_runs_api(project_id="p-1", limit=10)
    assert len(result.items) == 1
    assert result.items[0].run_id == "r-1"


def test_get_tender_analysis_detail_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_tender_analysis_detail",
        lambda _: TenderAnalysisDetailResponse(
            run=TenderAnalysisRunItem(
                run_id="r-1",
                project_id="p-1",
                document_id="d-1",
                filename="招标文件.pdf",
                status="SUCCEEDED",
                created_at="2026-02-14T00:00:00",
            ),
            summary=TenderAnalysisSummary(
                total_items=2,
                category_counts={"BIDDING_POINTS": 1, "SCORING_POINTS": 1},
                key_sections=["第一章"],
                warnings=[],
            ),
            key_infos=[
                TenderKeyInfoItem(
                    id="k1",
                    category="BIDDING_POINTS",
                    title="第一章",
                    content="必须提供资质证明",
                    page_no=1,
                    section_anchor="第一章",
                    score_weight=None,
                    is_must=True,
                    importance=80,
                )
            ],
        ),
    )
    result = routes.get_tender_analysis_detail_api("r-1")
    assert result.summary.total_items == 2
    assert result.key_infos[0].category == "BIDDING_POINTS"


def test_analyze_tender_upload_route(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "analyze_and_persist_tender_pdf",
        lambda **_: (
            TenderAnalysisRunItem(
                run_id="r-2",
                project_id="p-2",
                document_id="d-2",
                filename="analysis.pdf",
                status="SUCCEEDED",
                created_at="2026-02-14T00:00:00",
            ),
            TenderAnalysisSummary(
                total_items=3,
                category_counts={"COMPLIANCE_REQUIREMENTS": 2, "SCORING_POINTS": 1},
                key_sections=["第二章"],
                warnings=[],
            ),
        ),
    )

    async def _run() -> None:
        file = UploadFile(filename="analysis.pdf", file=BytesIO(b"%PDF-1.4"))
        result = await routes.analyze_tender_upload(file=file, project_id="p-2", created_by="tester")
        assert result.run_id == "r-2"
        assert result.summary.total_items == 3

    asyncio.run(_run())
