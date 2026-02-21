from __future__ import annotations

from pathlib import Path

from app.api import routes
from app.db.session import SessionLocal
from app.models.tables import WorkflowRun
from app.schemas.contracts import OutlineCreateRequest
from app.worker import tasks


def test_outline_create_initializes_v11_run_fields() -> None:
    created = routes.create_outline(
        OutlineCreateRequest(project_id="p-v11-run", tender_text="第一章 总则。必须满足资质。")
    )

    with SessionLocal() as db:
        row = db.query(WorkflowRun).filter(WorkflowRun.id == created.outline_id).first()

    assert row is not None
    assert row.current_step == "G0"
    assert row.step_status == "paused"
    assert row.resume_from_step == "G1"
    assert row.retry_count == 0
    assert row.last_error is None


def test_workflow_gate_artifact_roundtrip(tmp_path, monkeypatch) -> None:
    from app.services import workflow_artifacts

    monkeypatch.setattr(workflow_artifacts.settings, "workflow_artifact_dir", str(tmp_path))

    saved = workflow_artifacts.persist_gate_artifact(
        outline_id="outline-1",
        section_key="S-001",
        gate="G2",
        payload={"status": "SUPPORTED", "value": 1},
    )
    loaded = workflow_artifacts.load_gate_artifact("outline-1", "S-001", "G2")

    assert Path(saved).exists()
    assert loaded == {"status": "SUPPORTED", "value": 1}


def test_generate_stage_skips_execution_when_resuming_from_g3(monkeypatch, tmp_path) -> None:
    from app.services import workflow_artifacts

    monkeypatch.setattr(workflow_artifacts.settings, "workflow_artifact_dir", str(tmp_path))
    monkeypatch.setattr(tasks.section_generate_stage_task, "update_state", lambda *args, **kwargs: None)

    called = {"generate": 0}

    def _fake_generate_stage(**kwargs):  # noqa: ANN003
        called["generate"] += 1
        return {"status": "SUPPORTED", "generated_text": "should-not-run"}

    monkeypatch.setattr(tasks, "_generate_stage", _fake_generate_stage, raising=False)

    workflow_artifacts.persist_gate_artifact(
        outline_id="outline-2",
        section_key="S-002",
        gate="G2",
        payload={"status": "SUPPORTED", "generated_text": "from-artifact"},
    )

    context = {
        "outline_id": "outline-2",
        "project_id": "p-v11",
        "section_key": "S-002",
        "requirement_text": "必须满足工期要求",
        "industry_tag": None,
        "resume_from_step": "G3",
        "stages": {"extract": {"status": "OK"}},
    }

    result = tasks.section_generate_stage_task.run(context)

    assert called["generate"] == 0
    assert result["stages"]["generate"]["generated_text"] == "from-artifact"
