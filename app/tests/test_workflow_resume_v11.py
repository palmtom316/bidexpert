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


def test_extract_stage_uses_cached_gate_artifact_for_duplicate_delivery(monkeypatch, tmp_path) -> None:
    from app.services import workflow_artifacts

    monkeypatch.setattr(workflow_artifacts.settings, "workflow_artifact_dir", str(tmp_path))
    monkeypatch.setattr(tasks.section_extract_stage_task, "update_state", lambda *args, **kwargs: None)

    called = {"extract": 0}

    def _fake_extract_stage(_text: str) -> dict:  # noqa: ANN001
        called["extract"] += 1
        return {"status": "OK", "requirements": [{"code": "R-1"}]}

    monkeypatch.setattr(tasks, "_extract_stage", _fake_extract_stage, raising=False)

    workflow_artifacts.persist_gate_artifact(
        outline_id="outline-3",
        section_key="S-003",
        gate="G1",
        payload={"extract": {"status": "CACHED", "requirements": []}, "global_facts": {"project_name": "cached"}},
    )

    result = tasks.section_extract_stage_task.run(
        "outline-3",
        "p-v11",
        "S-003",
        "必须满足资质要求",
        None,
        "G1",
    )

    assert called["extract"] == 0
    assert result["stages"]["extract"]["status"] == "CACHED"
    assert result["global_facts"]["project_name"] == "cached"


def test_section_stage_tasks_enable_autoretry_backoff() -> None:
    registry = tasks.celery_app.tasks
    stage_names = [
        "tasks.section_extract_stage",
        "tasks.section_generate_stage",
        "tasks.section_validate_stage",
        "tasks.section_render_stage",
    ]

    for name in stage_names:
        task_obj = registry[name]
        autoretry_for = tuple(getattr(task_obj, "autoretry_for", ()) or ())
        assert RuntimeError in autoretry_for
        assert OSError in autoretry_for
        assert bool(getattr(task_obj, "retry_backoff", False)) is True
        assert int(getattr(task_obj, "retry_backoff_max", 0)) > 0
        assert bool(getattr(task_obj, "retry_jitter", False)) is True
