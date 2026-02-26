from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import GenerationVersion, MandatoryClause, Project, SectionContent


def test_addendum_overrides_mandatory_clause_by_clause_no() -> None:
    from app.services.addendum_parser import persist_addendum_payload
    from app.services.mandatory_clause_service import compute_effective_mandatory_clauses

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add_all(
            [
                MandatoryClause(project_id=project.id, clause_code="MC-001", clause_text="base-text-1"),
                MandatoryClause(project_id=project.id, clause_code="MC-002", clause_text="base-text-2"),
            ]
        )
        db.flush()

        addendum = persist_addendum_payload(
            db,
            project_id=project.id,
            tender_id="T-1",
            addendum_code="ADD-001",
            payload={
                "overrides": [
                    {
                        "clause_no": "MC-001",
                        "override_text": "override-text-1",
                        "impacted_chapters": ["CH-1"],
                    }
                ]
            },
        )

        effective = compute_effective_mandatory_clauses(db, project_id=project.id, addendum=addendum)

    assert effective["MC-001"]["clause_text"] == "override-text-1"
    assert effective["MC-001"]["source"] == "addendum"
    assert effective["MC-002"]["clause_text"] == "base-text-2"
    assert effective["MC-002"]["source"] == "base"


def test_addendum_marks_generated_chapters_stale(tmp_path: Path) -> None:
    from app.api.endpoints import tender as tender_endpoint
    from app.services.mandatory_clause_service import mark_generated_chapters_stale

    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        old_version = GenerationVersion(project_id=project.id, version_no=1, created_by="u")
        latest_version = GenerationVersion(project_id=project.id, version_no=2, created_by="u")
        db.add_all([old_version, latest_version])
        db.flush()

        db.add_all(
            [
                SectionContent(
                    project_id=project.id,
                    version_id=old_version.id,
                    section_key="CH-2",
                    section_title="chapter-2-old",
                    content_md="body",
                    content_json={"baseline": "old"},
                    created_by="u",
                ),
                SectionContent(
                    project_id=project.id,
                    version_id=latest_version.id,
                    section_key="CH-1",
                    section_title="chapter-1-latest",
                    content_md="body",
                    content_json={"x": 1},
                    created_by="u",
                ),
                SectionContent(
                    project_id=project.id,
                    version_id=latest_version.id,
                    section_key="CH-2",
                    section_title="chapter-2-latest",
                    content_md="body",
                    content_json={"baseline": "latest"},
                    created_by="u",
                ),
            ]
        )
        db.flush()

        stale_sections = mark_generated_chapters_stale(
            db,
            project_id=project.id,
            chapter_keys=["CH-2"],
            addendum_code="ADD-002",
        )

        saved_latest = db.execute(
            select(SectionContent).where(
                SectionContent.project_id == project.id,
                SectionContent.version_id == latest_version.id,
                SectionContent.section_key == "CH-2",
            )
        ).scalars().first()
        saved_old = db.execute(
            select(SectionContent).where(
                SectionContent.project_id == project.id,
                SectionContent.version_id == old_version.id,
                SectionContent.section_key == "CH-2",
            )
        ).scalars().first()

    assert stale_sections == ["CH-2"]
    assert saved_latest is not None
    assert saved_latest.content_json["stale_due_to_addendum"] is True
    assert saved_latest.content_json["stale_addendum_code"] == "ADD-002"
    assert saved_old is not None
    assert saved_old.content_json == {"baseline": "old"}

    workspace = tmp_path / str(uuid.uuid4())
    derived_dir = workspace / "derived"
    derived_dir.mkdir(parents=True)
    (derived_dir / "addendum_alert.json").write_text(
        json.dumps({"has_addendum_alert": True, "stale_chapters": ["CH-2"]}),
        encoding="utf-8",
    )

    run = SimpleNamespace(
        id=uuid.uuid4(),
        project_id=None,
        tender_id="T-1",
        filename="demo.zip",
        current_step=SimpleNamespace(value="READY_FOR_WRITING"),
        workspace_path=str(workspace),
        fatal_blocked_reason={"reasons": ["missing-license"]},
        error_detail=None,
        created_at=datetime.now(timezone.utc),
    )
    item = tender_endpoint._build_tender_import_run_item(run)

    assert item.fatal_blocked_reason == {"reasons": ["missing-license"]}
    assert item.addendum_alert is True
    assert item.stale_chapters == ["CH-2"]
