from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import BidAssetPool, Project
from app.services.bid_asset_pool_service import list_project_asset_pool
from app.services.personnel_matcher import match_personnel_team


def test_bid_asset_pool_prevents_cross_project_entity_usage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        p1 = Project(name="A", owner_user_id="u")
        p2 = Project(name="B", owner_user_id="u")
        db.add_all([p1, p2])
        db.flush()

        db.add_all(
            [
                BidAssetPool(
                    project_id=p1.id,
                    asset_name="P1-asset",
                    ownership_role="leader",
                    metadata_json={"asset_type": "person", "roles": ["项目经理"]},
                ),
                BidAssetPool(
                    project_id=p2.id,
                    asset_name="P2-asset",
                    ownership_role="leader",
                    metadata_json={"asset_type": "person", "roles": ["项目经理"]},
                ),
            ]
        )
        db.flush()

        p1_assets = list_project_asset_pool(db, project_id=p1.id, ownership_roles=["leader"], asset_type="person")

    assert len(p1_assets) == 1
    assert p1_assets[0]["asset_name"] == "P1-asset"


def test_personnel_matcher_enforces_social_security_and_no_active_project() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="A", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add_all(
            [
                BidAssetPool(
                    project_id=project.id,
                    asset_name="Alice",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["项目经理"],
                        "social_security_months": 12,
                        "active_project_count": 1,
                        "match_score": 90,
                    },
                ),
                BidAssetPool(
                    project_id=project.id,
                    asset_name="Bob",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["项目经理"],
                        "social_security_months": 4,
                        "active_project_count": 0,
                        "match_score": 80,
                    },
                ),
                BidAssetPool(
                    project_id=project.id,
                    asset_name="Carol",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["项目经理"],
                        "social_security_months": 8,
                        "active_project_count": 0,
                        "match_score": 70,
                        "evidence_refs": ["ss-proof", "cert-proof"],
                    },
                ),
            ]
        )
        db.flush()

        result = match_personnel_team(
            db,
            project_id=project.id,
            ownership_roles=["leader"],
            role_requirements=[
                {"role": "项目经理", "social_security_months": 6, "no_active_project": True},
            ],
        )

    assert result["matched"] is True
    assert result["missing_roles"] == []
    assert len(result["team"]) == 1
    assert result["team"][0]["asset_name"] == "Carol"


def test_personnel_matcher_returns_best_team_combination() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="A", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add_all(
            [
                BidAssetPool(
                    project_id=project.id,
                    asset_name="PM-A",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["项目经理"],
                        "social_security_months": 12,
                        "active_project_count": 0,
                        "match_score": 70,
                    },
                ),
                BidAssetPool(
                    project_id=project.id,
                    asset_name="PM-B",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["项目经理"],
                        "social_security_months": 12,
                        "active_project_count": 0,
                        "match_score": 95,
                    },
                ),
                BidAssetPool(
                    project_id=project.id,
                    asset_name="Safety-A",
                    ownership_role="leader",
                    metadata_json={
                        "asset_type": "person",
                        "roles": ["安全员"],
                        "social_security_months": 12,
                        "active_project_count": 0,
                        "match_score": 85,
                    },
                ),
            ]
        )
        db.flush()

        result = match_personnel_team(
            db,
            project_id=project.id,
            ownership_roles=["leader"],
            role_requirements=[
                {"role": "项目经理", "social_security_months": 6, "no_active_project": True},
                {"role": "安全员", "social_security_months": 6, "no_active_project": True},
            ],
        )

    assert result["matched"] is True
    assert sorted(item["asset_name"] for item in result["team"]) == ["PM-B", "Safety-A"]
    assert result["total_score"] == 180.0


def test_personnel_matcher_marks_missing_when_duplicate_role_demand_exceeds_supply() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="A", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add(
            BidAssetPool(
                project_id=project.id,
                asset_name="Only-PM",
                ownership_role="leader",
                metadata_json={
                    "asset_type": "person",
                    "roles": ["项目经理"],
                    "social_security_months": "12",
                    "active_project_count": "0",
                    "match_score": "88.5",
                },
            )
        )
        db.flush()

        result = match_personnel_team(
            db,
            project_id=project.id,
            ownership_roles=["leader"],
            role_requirements=[
                {"role": "项目经理", "social_security_months": 6, "no_active_project": True},
                {"role": "项目经理", "social_security_months": 6, "no_active_project": True},
            ],
        )

    assert result["matched"] is False
    assert result["missing_roles"] == ["项目经理"]
    assert len(result["team"]) == 1
