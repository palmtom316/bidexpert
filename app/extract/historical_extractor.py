from __future__ import annotations

import hashlib
from typing import Any

from app.core.config import settings
from app.schemas.contracts import EvidenceUpsertItem
from app.services.byok import resolve_profile_chain_for_task

_PROMPT_DESCRIPTION = (
    "从投标文件中提取可复用的专家知识片段。"
    "仅提取原文可定位内容，不要改写，不要重叠。"
    "输出按出现顺序组织，并给出类别。"
)


def _run_langextract(text: str, model_id: str) -> list[Any]:
    import langextract as lx

    example = lx.data.ExampleData(
        text="投标人须具备ISO9001认证，并在近三年完成不少于5个同类项目。",
        extractions=[
            lx.data.Extraction(
                extraction_class="资质要求",
                extraction_text="投标人须具备ISO9001认证",
                attributes={"section_anchor": "资质条件"},
            ),
            lx.data.Extraction(
                extraction_class="业绩要求",
                extraction_text="近三年完成不少于5个同类项目",
                attributes={"section_anchor": "业绩条件"},
            ),
        ],
    )
    result = lx.extract(
        text_or_documents=text,
        prompt_description=_PROMPT_DESCRIPTION,
        examples=[example],
        model_id=model_id,
    )
    return list(getattr(result, "extractions", []))


def _field(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _chunk_id(index: int, extraction_text: str) -> str:
    digest = hashlib.sha1(extraction_text.encode("utf-8")).hexdigest()[:12]
    return f"lx-{index}-{digest}"


def extract_evidence_chunks_from_text(
    *,
    text: str,
    industry_tag: str | None = None,
    doc_type: str = "EXPERT_HISTORY",
    model_id: str | None = None,
    project_id: str | None = None,
) -> list[EvidenceUpsertItem]:
    if not text.strip():
        raise ValueError("text must not be empty")

    model_candidates: list[str] = []
    preferred_model = (model_id or "").strip()
    if preferred_model:
        model_candidates.append(preferred_model)
    for profile in resolve_profile_chain_for_task(project_id=project_id, task_type="EXTRACT"):
        if profile.model not in model_candidates:
            model_candidates.append(profile.model)
    if settings.langextract_default_model not in model_candidates:
        model_candidates.append(settings.langextract_default_model)

    raw: list[Any] = []
    last_error: Exception | None = None
    for candidate in model_candidates:
        try:
            raw = _run_langextract(text=text, model_id=candidate)
            last_error = None
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    if last_error is not None and not raw:
        raise last_error

    chunks: list[EvidenceUpsertItem] = []
    for index, item in enumerate(raw, start=1):
        extraction_text = str(_field(item, "extraction_text", "")).strip()
        if not extraction_text:
            continue
        extraction_class = _field(item, "extraction_class")
        attributes = _field(item, "attributes", {}) or {}
        section_anchor = None
        if isinstance(attributes, dict):
            section_anchor = attributes.get("section_anchor")
        chunks.append(
            EvidenceUpsertItem(
                chunk_id=_chunk_id(index, extraction_text),
                text=extraction_text,
                doc_type=doc_type,
                section_type=str(extraction_class) if extraction_class else None,
                industry_tag=industry_tag,
                source_locator={"section_anchor": section_anchor} if section_anchor else None,
            )
        )
    return chunks
