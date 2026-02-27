"""G0-G8 GenerationRun idempotent orchestrator with resume support."""
from __future__ import annotations

import enum
import logging
from datetime import UTC, datetime

from app.db.session import session_scope
from app.models.tables import GenerationRun

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


class GenerationStep(str, enum.Enum):
    G2_REDLINE = "G2_REDLINE"
    G3_SCORECARD = "G3_SCORECARD"
    G4_OUTLINE = "G4_OUTLINE"
    G5_GENERATE = "G5_GENERATE"
    G6_SCORING = "G6_SCORING"
    G7_EXPORT = "G7_EXPORT"
    G8_FEEDBACK = "G8_FEEDBACK"


_STEP_ORDER = list(GenerationStep)


def _step_index(step: GenerationStep) -> int:
    return _STEP_ORDER.index(step)


def _is_blocked(run: GenerationRun) -> bool:
    """Check if the run has a P0 blocking status from redline checks."""
    output = dict(run.output_json or {})
    return output.get("redline_status") == "BLOCKED"


def run_step(
    generation_run_id: str,
    step: GenerationStep,
    *,
    executor: dict | None = None,
) -> dict:
    """Execute a single step idempotently.

    Returns dict with keys: step, status, skipped, error.
    """
    with session_scope() as db:
        run = (
            db.query(GenerationRun)
            .filter(GenerationRun.id == generation_run_id)
            .with_for_update()
            .first()
        )
        if not run:
            raise ValueError(f"GenerationRun not found: {generation_run_id}")

        output = dict(run.output_json or {})
        step_results = dict(output.get("step_results") or {})

        # Already succeeded — skip
        if step_results.get(step.value, {}).get("status") == "success":
            return {"step": step.value, "status": "skipped", "skipped": True, "error": None}

        # P0 blocking — refuse to advance past G4
        if _is_blocked(run) and _step_index(step) > _step_index(GenerationStep.G4_OUTLINE):
            return {
                "step": step.value,
                "status": "blocked",
                "skipped": False,
                "error": "P0 redline blocks advancement past G4",
            }

        # Max retries exceeded
        current_retries = step_results.get(step.value, {}).get("retry_count", 0)
        if current_retries >= _MAX_RETRIES:
            return {
                "step": step.value,
                "status": "max_retries",
                "skipped": False,
                "error": f"step exhausted {_MAX_RETRIES} retries",
            }

        # Execute step
        run.current_step = step.value
        run.step_status = "running"
        run.updated_at = datetime.now(UTC)
        db.flush()

        try:
            step_output = _execute_step(step, run, executor)
            step_results[step.value] = {
                "status": "success",
                "retry_count": current_retries,
                "output": step_output,
            }
            run.step_status = "success"
            run.error_detail = None

            # Advance resume pointer to next step
            next_idx = _step_index(step) + 1
            if next_idx < len(_STEP_ORDER):
                run.resume_from_step = _STEP_ORDER[next_idx].value
            else:
                run.status = "COMPLETED"
                run.resume_from_step = step.value

        except Exception as exc:
            step_results[step.value] = {
                "status": "failed",
                "retry_count": current_retries + 1,
                "error": str(exc),
            }
            run.step_status = "failed"
            run.error_detail = str(exc)[:2000]
            run.retry_count = int(run.retry_count or 0) + 1
            run.resume_from_step = step.value
            logger.warning("step %s failed for run %s: %s", step.value, generation_run_id, exc)

        output["step_results"] = step_results
        run.output_json = output
        run.updated_at = datetime.now(UTC)
        db.add(run)
        db.commit()

        result_entry = step_results[step.value]
        return {
            "step": step.value,
            "status": result_entry["status"],
            "skipped": False,
            "error": result_entry.get("error"),
        }


def resume_run(generation_run_id: str, *, executor: dict | None = None) -> list[dict]:
    """Resume a run from its saved resume_from_step, executing all remaining steps."""
    with session_scope() as db:
        run = db.query(GenerationRun).filter(GenerationRun.id == generation_run_id).first()
        if not run:
            raise ValueError(f"GenerationRun not found: {generation_run_id}")
        resume_step_value = str(run.resume_from_step or "").strip()

    # Find starting step
    start_idx = 0
    for idx, s in enumerate(_STEP_ORDER):
        if s.value == resume_step_value:
            start_idx = idx
            break

    results: list[dict] = []
    for step in _STEP_ORDER[start_idx:]:
        result = run_step(generation_run_id, step, executor=executor)
        results.append(result)
        if result["status"] in ("failed", "blocked", "max_retries"):
            break

    return results


def _execute_step(step: GenerationStep, run: GenerationRun, executor: dict | None) -> dict:
    """Dispatch to the appropriate step handler.

    If an executor dict is provided (keyed by step name), use the provided callable.
    Otherwise use a no-op placeholder that records step execution.
    """
    if executor and step.value in executor:
        handler = executor[step.value]
        return handler(run)

    # Default no-op for steps not yet wired
    return {"executed": True, "step": step.value, "placeholder": True}
