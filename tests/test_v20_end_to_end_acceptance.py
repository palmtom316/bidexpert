"""DoD acceptance tests covering Bidexpert V2.0 delivery document Section 7."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import BidAssetPool, Project
from app.schemas.contracts import (
    RedlineCheckRequest,
    RedlineDurationCheck,
    RedlineFinding,
    RedlineParameterComparison,
)
from app.services.entity_assembly import render_bid_asset_pool_markdown_table
from app.services.frozen_block_guard import build_frozen_block_signatures, verify_frozen_block_signatures
from app.services.redline_engine import run_redline_check


# ── 1. Negative deviation P0 blocks generation ──────────────


def test_negative_deviation_p0_blocks_generation():
    """A parameter negative deviation must produce P0 and BLOCKED status."""
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
        parameter_comparisons=[
            RedlineParameterComparison(
                parameter_name="最低注册资本",
                required_value=500,
                provided_value=200,
                unit="万元",
            ),
        ],
    )
    report = run_redline_check(payload)
    assert report.status == "BLOCKED"
    neg_dev = [f for f in report.findings if f.rule_id.startswith("NEG-DEV")]
    assert len(neg_dev) == 1
    assert neg_dev[0].severity == "P0"
    assert "200" in neg_dev[0].message
    assert "500" in neg_dev[0].message


# ── 2. Readiness dashboard renders missing items ────────────


def test_readiness_dashboard_renders_missing_items():
    """Missing documents and P0/P1 findings populate readiness_missing_items."""
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
        findings=[
            RedlineFinding(
                rule_id="QUAL-MISSING",
                category="资质",
                severity="P0",
                message="未找到资质文件",
                required_action="上传资质文件",
            ),
        ],
        required_documents=["投标函", "授权委托书", "营业执照"],
        provided_documents=["投标函"],
    )
    report = run_redline_check(payload)
    assert report.status == "BLOCKED"
    assert len(report.readiness_missing_items) > 0
    # Should contain the required_action from the finding
    assert any("上传资质文件" in item for item in report.readiness_missing_items)
    # Should contain missing documents
    assert any("授权委托书" in item for item in report.readiness_missing_items)
    assert any("营业执照" in item for item in report.readiness_missing_items)
    # Should NOT contain already-provided documents
    assert not any("投标函" == item for item in report.readiness_missing_items)


# ── 3. Asset isolation: cross-project ───────────────────────


def test_asset_isolation_cross_project():
    """Project A's asset pool must not include Project B's entries."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        proj_a = Project(name="Project A", owner_user_id="u")
        proj_b = Project(name="Project B", owner_user_id="u")
        db.add_all([proj_a, proj_b])
        db.flush()

        db.add(
            BidAssetPool(
                project_id=proj_a.id,
                asset_name="A的资质",
                ownership_role="leader",
                metadata_json={"asset_type": "qualification", "evidence_refs": []},
            )
        )
        db.add(
            BidAssetPool(
                project_id=proj_b.id,
                asset_name="B的资质",
                ownership_role="leader",
                metadata_json={"asset_type": "qualification", "evidence_refs": []},
            )
        )
        db.flush()

        # Query Project A's pool
        markdown_a = render_bid_asset_pool_markdown_table(
            db,
            project_id=proj_a.id,
            asset_type="qualification",
        )
        # Query Project B's pool
        markdown_b = render_bid_asset_pool_markdown_table(
            db,
            project_id=proj_b.id,
            asset_type="qualification",
        )

    assert "A的资质" in markdown_a
    assert "B的资质" not in markdown_a
    assert "B的资质" in markdown_b
    assert "A的资质" not in markdown_b


# ── 4. Entity table not tampered by LLM ─────────────────────


def test_entity_table_not_tampered_by_llm():
    """Entity asset tables must be rendered via code templates, not LLM output."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add(
            BidAssetPool(
                project_id=project.id,
                asset_name="110kV项目",
                ownership_role="leader",
                metadata_json={
                    "asset_type": "performance",
                    "contract_amount": "5000",
                    "engineering_type": "变电",
                    "client": "国网",
                    "completion_date": "2024-01-01",
                    "evidence_refs": ["E1"],
                },
            )
        )
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="performance",
        )

    # Verify deterministic template structure (not LLM-generated)
    assert markdown.startswith("| 项目名称 |")
    assert "| --- |" in markdown
    lines = markdown.strip().split("\n")
    # Header + separator + at least 1 data row
    assert len(lines) >= 3
    # Data row must contain the exact asset values
    assert "110kV项目" in lines[2]
    assert "5000" in lines[2]


# ── 5. Frozen text integrity across pipeline ────────────────


def test_frozen_text_integrity_across_pipeline():
    """FROZEN blocks must remain byte-identical through build → verify cycle."""
    original_text = (
        "前言内容\n"
        "[FROZEN:LEGAL]本投标文件为正式法律文件，不得修改。[/FROZEN]\n"
        "中间段落\n"
        "[FROZEN:COMMITMENT]我方承诺遵守全部招标条件。[/FROZEN]\n"
        "结尾内容"
    )

    signatures = build_frozen_block_signatures(original_text)
    assert len(signatures) == 2
    assert "LEGAL" in signatures
    assert "COMMITMENT" in signatures

    # Identical text must pass verification
    verify_frozen_block_signatures(original_text, signatures)

    # Tampered text must fail
    tampered = original_text.replace("不得修改", "可以修改")
    with pytest.raises(ValueError, match="frozen block hash mismatch"):
        verify_frozen_block_signatures(tampered, signatures)

    # Missing block must fail
    missing = "前言内容\n中间段落\n结尾内容"
    with pytest.raises(ValueError, match="missing frozen block"):
        verify_frozen_block_signatures(missing, signatures)


# ── 6. Scoring outputs deductions and evidence map ──────────


def test_scoring_outputs_deductions_and_evidence_map():
    """Redline engine must produce findings with evidence_refs for deductions."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    quals = [
        {"id": "q-1", "title": "电力工程施工总承包", "doc_type": "QUALIFICATION", "valid_to": yesterday},
    ]

    from app.services.redline_engine import check_qualifications

    with patch("app.tender.assets.repository.get_company_qualifications", return_value=quals):
        findings = check_qualifications(
            project_id="proj-1",
            tender_package_id="pkg-1",
        )

    expired = [f for f in findings if "QUAL-EXPIRED" in f.rule_id]
    assert len(expired) == 1
    assert expired[0].severity == "P0"
    assert expired[0].evidence_refs  # Must include evidence references
    assert expired[0].required_action  # Must include required remediation action


# ── 7. Duration arithmetic mismatch blocks ──────────────────


def test_duration_arithmetic_mismatch_blocks():
    """Duration arithmetic inconsistency must produce P0 BLOCKED status."""
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
        duration_check=RedlineDurationCheck(
            committed_duration_days=100,
            start_date="2025-03-01",
            completion_date="2025-06-01",  # 92 days, not 100
        ),
    )
    report = run_redline_check(payload)
    assert report.status == "BLOCKED"
    duration_findings = [f for f in report.findings if f.rule_id == "DURATION-MISMATCH"]
    assert len(duration_findings) == 1
    assert duration_findings[0].severity == "P0"
    assert "100" in duration_findings[0].message
    assert "92" in duration_findings[0].message
