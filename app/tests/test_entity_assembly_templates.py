"""Tests for entity assembly specialized templates (performance + equipment)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import BidAssetPool, Project
from app.services.entity_assembly import render_bid_asset_pool_markdown_table


def _setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return engine


def test_performance_template_renders_correct_columns():
    engine = _setup_db()
    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add(
            BidAssetPool(
                project_id=project.id,
                asset_name="110kV 变电站新建工程",
                ownership_role="leader",
                metadata_json={
                    "asset_type": "performance",
                    "contract_amount": "3500",
                    "engineering_type": "变电工程",
                    "client": "国网电力公司",
                    "completion_date": "2024-06-15",
                    "evidence_refs": ["E-P-1"],
                },
            )
        )
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="performance",
        )

    assert "| 项目名称 | 合同金额(万元) | 工程类型 | 建设单位 | 竣工日期 | 证据 |" in markdown
    assert "110kV 变电站新建工程" in markdown
    assert "3500" in markdown
    assert "变电工程" in markdown
    assert "国网电力公司" in markdown
    assert "2024-06-15" in markdown


def test_equipment_template_renders_correct_columns():
    engine = _setup_db()
    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add(
            BidAssetPool(
                project_id=project.id,
                asset_name="主变压器",
                ownership_role="member",
                metadata_json={
                    "asset_type": "equipment",
                    "spec_model": "SZ11-31500/110",
                    "quantity": "2",
                    "tech_params": "110kV/10.5kV",
                    "evidence_refs": ["E-E-1"],
                },
            )
        )
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="equipment",
        )

    assert "| 设备名称 | 规格型号 | 数量 | 技术参数 | 归属角色 | 证据 |" in markdown
    assert "主变压器" in markdown
    assert "SZ11-31500/110" in markdown
    assert "2" in markdown
    assert "member" in markdown


def test_generic_fallback_template_still_works():
    engine = _setup_db()
    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add(
            BidAssetPool(
                project_id=project.id,
                asset_name="安全生产许可证",
                ownership_role="leader",
                metadata_json={
                    "asset_type": "qualification",
                    "evidence_refs": ["E-Q-1"],
                },
            )
        )
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="qualification",
        )

    assert "| 资产名称 | 归属角色 | 资产类型 | 证据 |" in markdown
    assert "安全生产许可证" in markdown
    assert "leader" in markdown


def test_performance_empty_returns_placeholder():
    engine = _setup_db()
    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="performance",
        )

    assert "| 项目名称 |" in markdown
    assert "(无)" in markdown


def test_equipment_empty_returns_placeholder():
    engine = _setup_db()
    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="equipment",
        )

    assert "| 设备名称 |" in markdown
    assert "(无)" in markdown
