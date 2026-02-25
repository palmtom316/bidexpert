"""Blueprint builder — generate bid blueprint with P00 mandatory tasks (R1, R2, R6)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.tender.schemas import BidBlueprint, BlueprintTask, RetrievalPolicy

logger = logging.getLogger(__name__)


def build_blueprint(
    *,
    tender_id: str,
    manifest: dict,
    derived_dir: Path,
) -> BidBlueprint:
    """Build the bid blueprint from all derived artefacts.

    R1: Administrative checklist as P00 task.
    R2: Deviation table generation as P00 task.
    R6: Hard filters (voltage_level, engineering_type) in retrieval_policy.
    """
    tasks: list[BlueprintTask] = []
    admin_checklist: list[str] = []
    task_idx = 0

    # ── R1: P00 — Administrative checklist ──
    fmt_path = derived_dir / "format_signature_constraints.json"
    if fmt_path.exists():
        fmt_data = json.loads(fmt_path.read_text(encoding="utf-8"))
        if fmt_data.get("paper_copies"):
            admin_checklist.append(f"正本 {fmt_data['paper_copies']} 份")
        if fmt_data.get("electronic_copies"):
            admin_checklist.append(f"电子版 {fmt_data['electronic_copies']} 份")
        if fmt_data.get("binding_method"):
            admin_checklist.append(f"装订方式: {fmt_data['binding_method']}")
        for seal in fmt_data.get("seal_requirements", [])[:10]:
            admin_checklist.append(f"签章: {seal}")
        for env in fmt_data.get("envelope_requirements", [])[:5]:
            admin_checklist.append(f"封装: {env}")

    task_idx += 1
    tasks.append(BlueprintTask(
        task_id=f"T-{task_idx:03d}",
        priority="P00",
        title="行政合规检查清单",
        description="检查投标文件份数、签章、密封等行政要求。必须在提交前逐项确认。",
        section_key="administrative",
    ))

    # ── R2: P00 — Deviation tables ──
    task_idx += 1
    tasks.append(BlueprintTask(
        task_id=f"T-{task_idx:03d}",
        priority="P00",
        title="生成偏离表",
        description="基于技术和商务要求生成偏离表。必须在投标文件编写前完成。",
        section_key="deviation_tables",
    ))

    # ── Generate section tasks from scoring model ──
    scoring_path = derived_dir / "scoring_model.json"
    if scoring_path.exists():
        scoring_data = json.loads(scoring_path.read_text(encoding="utf-8"))
        for item in scoring_data.get("items", []):
            task_idx += 1
            priority = "P01" if item.get("max_score", 0) >= 15 else "P02"
            tasks.append(BlueprintTask(
                task_id=f"T-{task_idx:03d}",
                priority=priority,
                title=f"编写: {item.get('category', 'section')} (分值 {item.get('max_score', 0)})",
                description=item.get("description", "")[:300],
                section_key=item.get("category", ""),
                depends_on=["T-001", "T-002"],  # Depends on admin check + deviation tables
            ))

    # ── Generate tasks from technical requirements ──
    tech_path = derived_dir / "technical_requirements.json"
    if tech_path.exists():
        tech_data = json.loads(tech_path.read_text(encoding="utf-8"))
        mandatory_reqs = [r for r in tech_data.get("requirements", []) if r.get("is_mandatory")]
        if mandatory_reqs:
            task_idx += 1
            tasks.append(BlueprintTask(
                task_id=f"T-{task_idx:03d}",
                priority="P01",
                title="响应强制技术要求",
                description=f"{len(mandatory_reqs)} 项强制技术要求需逐项响应",
                section_key="technical_response",
                depends_on=["T-002"],
            ))

    # ── Build retrieval policy with hard filters (R6) ──
    hard_filters: dict[str, str] = {}
    voltage = manifest.get("voltage_level")
    if voltage:
        hard_filters["voltage_level"] = voltage
    eng_type = manifest.get("project_type")
    if eng_type:
        hard_filters["engineering_type"] = eng_type
    region = manifest.get("region")
    if region:
        hard_filters["region"] = region

    # Also extract voltage from technical requirements
    if tech_path.exists() and "voltage_level" not in hard_filters:
        tech_data = json.loads(tech_path.read_text(encoding="utf-8"))
        for req in tech_data.get("requirements", []):
            vl = req.get("voltage_level")
            if vl:
                hard_filters["voltage_level"] = vl
                break

    retrieval_policy = RetrievalPolicy(
        hard_filters=hard_filters,
        preferred_tags=[manifest.get("project_type", ""), manifest.get("region", "")],
    )

    logger.info("blueprint: %d tasks, %d admin items, filters=%s", len(tasks), len(admin_checklist), hard_filters)

    return BidBlueprint(
        tender_id=tender_id,
        tasks=tasks,
        retrieval_policy=retrieval_policy,
        administrative_checklist=admin_checklist,
    )
