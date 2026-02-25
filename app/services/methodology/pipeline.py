from __future__ import annotations

import json
from pathlib import Path
from datetime import UTC, datetime

from app.core.config import settings
from app.models.tables import MethodologyReviewStatus, MethodologyRiskLevel, MethodologyRunStep
from app.services.methodology.repository import create_methodology_run, update_methodology_run
from app.services.methodology.rewrite_and_extract import extract_methodology_assets
from app.services.methodology.risk_scan import assess_source_risk
from app.services.methodology.sanitize import remove_pii
from app.services.methodology.similarity import evaluate_similarity
from app.services.ingest.file_router import ingest_upload_bytes


def _run_dir(run_id: str) -> Path:
    base = Path(settings.methodology_storage_dir)
    target = base / "runs" / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def execute_methodology_pipeline(*, run_id: str, domain: str | None, tags: list[str] | None) -> None:
    from app.services.methodology.repository import get_methodology_run

    run = get_methodology_run(run_id)
    if run is None:
        raise ValueError("run not found")

    text = run.input_text or ""
    sanitized = remove_pii(text)
    run_dir = _run_dir(run_id)
    sanitized_path = run_dir / "sanitized_input.txt"
    sanitized_path.write_text(sanitized.sanitized_text, encoding="utf-8")

    risk = assess_source_risk(
        source_type=run.source_type,
        findings=sanitized.findings,
        pii_removed=sanitized.pii_removed,
    )

    update_methodology_run(
        run_id,
        step=MethodologyRunStep.SANITIZED,
        progress=35,
        sanitized_input_path=str(sanitized_path),
        pii_removed=sanitized.pii_removed,
        findings_json={"items": sanitized.findings},
        risk_level=MethodologyRiskLevel(risk.risk_level),
    )

    if risk.blocked:
        update_methodology_run(
            run_id,
            status="NEED_EDIT",
            step=MethodologyRunStep.SCORED,
            progress=100,
            review_status=MethodologyReviewStatus.NEED_EDIT,
            review_comment=";".join(risk.reasons),
            updated_at=datetime.now(UTC),
        )
        return

    extracted = extract_methodology_assets(sanitized_text=sanitized.sanitized_text, domain=domain, tags=tags)
    similarity = evaluate_similarity(
        source_text=sanitized.sanitized_text,
        rewritten_text=extracted.get("template_md", ""),
        threshold=float(settings.methodology_similarity_threshold),
    )

    payload = {
        **extracted,
        "quality": {
            "rewrite_similarity_score": similarity.score,
            "pii_removed": sanitized.pii_removed,
            "risk_level": risk.risk_level,
        },
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    review_status = MethodologyReviewStatus.NEED_EDIT if similarity.decision == "need_edit" else MethodologyReviewStatus.PENDING
    status = "NEED_EDIT" if review_status == MethodologyReviewStatus.NEED_EDIT else "READY_FOR_REVIEW"

    update_methodology_run(
        run_id,
        status=status,
        step=MethodologyRunStep.READY_FOR_REVIEW,
        progress=100,
        output_json_path=str(result_path),
        similarity_score=similarity.score,
        review_status=review_status,
    )


def create_methodology_extract_run(
    *,
    text: str,
    source_type: str,
    source_note: str | None,
    domain: str | None,
    tags: list[str] | None,
    created_by: str,
) -> str:
    run_id = create_methodology_run(
        source_type=source_type,
        source_note=source_note,
        input_kind="text",
        input_text=text,
        created_by=created_by,
    )
    execute_methodology_pipeline(run_id=run_id, domain=domain, tags=tags)
    return run_id


def _decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def create_methodology_extract_run_from_file(
    *,
    filename: str,
    content: bytes,
    source_type: str,
    source_note: str | None,
    domain: str | None,
    tags: list[str] | None,
    created_by: str,
) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in {".md", ".markdown", ".txt"}:
        text = _decode_text_bytes(content)
    else:
        payload = ingest_upload_bytes(
            filename=filename,
            file_bytes=content,
            enable_ocr_fallback=settings.enable_ocr_fallback,
        )
        text = payload.full_text

    run_id = create_methodology_run(
        source_type=source_type,
        source_note=source_note,
        input_kind="file",
        input_text=text,
        created_by=created_by,
    )
    execute_methodology_pipeline(run_id=run_id, domain=domain, tags=tags)
    return run_id
