"""Tests for GenerationRun idempotent orchestrator."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import GenerationRun, Project
from app.services.generation_run_orchestrator import (
    GenerationStep,
    resume_run,
    run_step,
)


def _setup_db_and_run():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    with Session(engine) as db:
        project = Project(name="Test", owner_user_id="u")
        db.add(project)
        db.flush()

        gen_run = GenerationRun(
            project_id=project.id,
            status="PENDING",
            current_step="RECEIVED",
            step_status="paused",
            resume_from_step="G2_REDLINE",
            input_json={},
            output_json={},
        )
        db.add(gen_run)
        db.commit()
        run_id = str(gen_run.id)
    return engine, run_id


def _patch_session_scope(monkeypatch, engine):
    """Patch session_scope to use our in-memory engine."""
    from contextlib import contextmanager

    @contextmanager
    def _test_session_scope():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr(
        "app.services.generation_run_orchestrator.session_scope",
        _test_session_scope,
    )


def test_run_step_executes_and_succeeds(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    result = run_step(run_id, GenerationStep.G2_REDLINE)
    assert result["status"] == "success"
    assert result["skipped"] is False


def test_run_step_skips_already_succeeded(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    run_step(run_id, GenerationStep.G2_REDLINE)
    result = run_step(run_id, GenerationStep.G2_REDLINE)
    assert result["status"] == "skipped"
    assert result["skipped"] is True


def test_run_step_blocks_past_g4_on_p0(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    # Set P0 blocked status in output_json
    with Session(engine) as db:
        gen_run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
        gen_run.output_json = {"redline_status": "BLOCKED"}
        db.commit()

    result = run_step(run_id, GenerationStep.G5_GENERATE)
    assert result["status"] == "blocked"
    assert "P0" in result["error"]


def test_run_step_records_failure_and_increments_retry(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    def _failing_handler(run):
        raise RuntimeError("simulated failure")

    executor = {"G2_REDLINE": _failing_handler}
    result = run_step(run_id, GenerationStep.G2_REDLINE, executor=executor)
    assert result["status"] == "failed"
    assert "simulated failure" in result["error"]

    with Session(engine) as db:
        gen_run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
        assert gen_run.retry_count == 1
        assert gen_run.resume_from_step == "G2_REDLINE"


def test_run_step_respects_max_retries(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    # Manually set retry count to max
    with Session(engine) as db:
        gen_run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
        gen_run.output_json = {
            "step_results": {"G2_REDLINE": {"status": "failed", "retry_count": 3, "error": "prev"}},
        }
        db.commit()

    result = run_step(run_id, GenerationStep.G2_REDLINE)
    assert result["status"] == "max_retries"


def test_resume_run_executes_remaining_steps(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    results = resume_run(run_id)
    assert len(results) == 7  # G2 through G8
    assert all(r["status"] == "success" for r in results)

    # Verify run is completed
    with Session(engine) as db:
        gen_run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
        assert gen_run.status == "COMPLETED"


def test_resume_run_stops_on_failure(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    def _fail_at_g5(run):
        raise RuntimeError("G5 failed")

    executor = {"G5_GENERATE": _fail_at_g5}
    results = resume_run(run_id, executor=executor)

    statuses = [r["status"] for r in results]
    assert "failed" in statuses
    # Steps before G5 should succeed, G5 fails, nothing after
    g5_idx = next(i for i, r in enumerate(results) if r["step"] == "G5_GENERATE")
    assert all(r["status"] == "success" for r in results[:g5_idx])
    assert results[g5_idx]["status"] == "failed"
    assert len(results) == g5_idx + 1


def test_resume_run_from_midpoint(monkeypatch):
    engine, run_id = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    # Set resume point to G5
    with Session(engine) as db:
        gen_run = db.query(GenerationRun).filter(GenerationRun.id == run_id).first()
        gen_run.resume_from_step = "G5_GENERATE"
        # Mark earlier steps as done
        gen_run.output_json = {
            "step_results": {
                "G2_REDLINE": {"status": "success", "retry_count": 0, "output": {}},
                "G3_SCORECARD": {"status": "success", "retry_count": 0, "output": {}},
                "G4_OUTLINE": {"status": "success", "retry_count": 0, "output": {}},
            }
        }
        db.commit()

    results = resume_run(run_id)
    assert len(results) == 4  # G5, G6, G7, G8
    assert results[0]["step"] == "G5_GENERATE"
    assert all(r["status"] == "success" for r in results)


def test_run_step_not_found_raises(monkeypatch):
    engine, _ = _setup_db_and_run()
    _patch_session_scope(monkeypatch, engine)

    with pytest.raises(ValueError, match="not found"):
        run_step(str(uuid.uuid4()), GenerationStep.G2_REDLINE)
