from __future__ import annotations

from datetime import date, timedelta

from app.schemas.contracts import EvidenceUpsertItem
from app.services.expert_library import _build_structured_chunks
from app.services.knowledge_quality import collect_expiry_warnings, score_knowledge_quality
from app.services.quality_sampling import evaluate_quality_sampling


def test_quality_score_changes_with_timeliness_completeness_match_and_source() -> None:
    today = date.today()
    rich_text = (
        "电力施工企业具备一级资质，项目经理与安全员证书齐全，"
        "并提供近三年同类变电站业绩、质量管理制度和详细实施方案。"
    )
    poor_text = "资质证明"

    high = score_knowledge_quality(
        text=rich_text,
        source="manual_reviewed",
        industry_tag="电力",
        valid_to=(today + timedelta(days=540)).isoformat(),
        match_terms=["资质", "变电站", "质量管理"],
    )
    low = score_knowledge_quality(
        text=poor_text,
        source="fallback_block",
        industry_tag="电力",
        valid_to=(today - timedelta(days=1)).isoformat(),
        match_terms=["资质", "变电站", "质量管理"],
    )

    assert high.score > low.score
    assert high.timeliness > low.timeliness
    assert high.completeness > low.completeness
    assert high.relevance >= low.relevance
    assert high.source_reliability > low.source_reliability
    assert low.expiry_status == "expired"


def test_structured_chunks_apply_dynamic_score_and_expiry_penalty() -> None:
    today = date.today()
    near_expiry = (today + timedelta(days=5)).isoformat()

    chunks = _build_structured_chunks(
        category_key="COMPANY_QUALIFICATION",
        lines=[
            "企业持有 ISO9001 质量管理体系认证，有效期至 " + near_expiry,
            "企业具备同类项目履约能力和完整安全管理制度",
        ],
        industry_tag="电力",
    )

    assert len(chunks) == 2
    assert chunks[0].valid_to == near_expiry
    assert chunks[0].quality_score < chunks[1].quality_score

    warnings = collect_expiry_warnings(chunks, warning_days=30)
    assert any(w.startswith("evidence_near_expiry:") for w in warnings)


def test_quality_sampling_ratio_and_threshold_can_trigger_manual_review() -> None:
    chunks = [
        EvidenceUpsertItem(chunk_id=f"good-{idx}", text="合规内容", quality_score=92.0)
        for idx in range(1, 9)
    ]
    chunks.extend(
        [
            EvidenceUpsertItem(chunk_id="risk-1", text="已过期资质", quality_score=45.0, valid_to="2020-01-01"),
            EvidenceUpsertItem(chunk_id="risk-2", text="缺失关键参数", quality_score=52.0),
        ]
    )

    report = evaluate_quality_sampling(
        chunks,
        sampling_ratio=0.2,
        accuracy_threshold=0.9,
    )

    assert report.total_chunks == 10
    assert report.sampled_count >= 2
    assert report.manual_review_required is True
    assert any(item.sampled and item.risk_level == "high" for item in report.records)
