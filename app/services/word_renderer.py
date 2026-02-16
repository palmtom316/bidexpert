from __future__ import annotations

from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate

from app.core.config import settings


def ensure_default_template(path: Path) -> None:
    if path.exists():
        return
    doc = Document()
    doc.add_heading("投标文件", level=1)
    doc.add_paragraph("项目名称：{{project_name}}")
    doc.add_paragraph("技术方案：{{technical_plan}}")
    doc.add_paragraph("实施计划：{{implementation_plan}}")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))


def _safe_path(raw_path: str, base_dir: Path) -> Path:
    candidate = Path(raw_path)
    full_path = candidate if candidate.is_absolute() else (base_dir / candidate)

    resolved_base = base_dir.resolve()
    resolved_target = full_path.resolve(strict=False)
    try:
        resolved_target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"path is outside allowed directory: {resolved_base}") from exc
    return resolved_target


def render_word(output_path: str, placeholders: dict[str, str], template_path: str | None = None) -> str:
    template_root = Path(settings.render_template_dir)
    export_root = Path(settings.render_output_dir)
    template_root.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)

    template_candidate = template_path or "default_tender_template.docx"
    template_file = _safe_path(template_candidate, template_root)
    ensure_default_template(template_file)

    out = _safe_path(output_path, export_root)
    if out.suffix.lower() != ".docx":
        raise ValueError("output_path must end with .docx")
    out.parent.mkdir(parents=True, exist_ok=True)

    tpl = DocxTemplate(str(template_file))
    tpl.render(placeholders)
    tpl.save(str(out))
    return str(out)


def render_word_sections(
    output_path: str,
    sections: list[dict[str, str]],
    template_path: str | None = None,
    title: str = "投标文件",
) -> str:
    template_root = Path(settings.render_template_dir)
    export_root = Path(settings.render_output_dir)
    template_root.mkdir(parents=True, exist_ok=True)
    export_root.mkdir(parents=True, exist_ok=True)

    template_candidate = template_path or "default_tender_template.docx"
    template_file = _safe_path(template_candidate, template_root)
    ensure_default_template(template_file)

    out = _safe_path(output_path, export_root)
    if out.suffix.lower() != ".docx":
        raise ValueError("output_path must end with .docx")
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = Document(str(template_file))
    doc.add_heading(title, level=1)
    for idx, section in enumerate(sections, start=1):
        heading = section.get("title") or f"章节 {idx}"
        content = section.get("content") or ""
        doc.add_heading(heading, level=2)
        doc.add_paragraph(content)

    doc.save(str(out))
    return str(out)
