from __future__ import annotations

from app.api import routes
from app.schemas.contracts import DraftGenerationRequest
from app.services.generation_pipeline import generate_draft_with_retrieval
from app.services.qdrant_store import RetrievedEvidence


def test_budget_exceeded_does_not_block_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.generation_pipeline.decompose_requirement",
        lambda _: [],
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.retrieve_for_subrequirements",
        lambda **_: {},
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.merge_retrieval",
        lambda _: (
            ["e-1"],
            {"sub-1": ["e-1"]},
            [RetrievedEvidence(chunk_id="e-1", score=0.9, text="具备类似经验", payload={})],
        ),
    )
    monkeypatch.setattr(
        "app.services.generation_pipeline.reserve_budget_persistent",
        lambda **_: (False, 0),
    )

    result = generate_draft_with_retrieval(
        requirement_id="REQ-1",
        requirement_text="必须具备类似项目经验",
    )

    assert result.status != "BUDGET_EXCEEDED"


def test_generation_draft_blocks_pricing_content() -> None:
    payload = DraftGenerationRequest(
        requirement_id="REQ-2",
        requirement_text="请按报价表给出总价与税率",
    )
    result = routes.generate_draft(payload)
    assert result.status == "BLOCKED_PRICING_CONTENT"
