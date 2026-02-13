from __future__ import annotations

from pathlib import Path

from docx import Document
from docxtpl import DocxTemplate


def ensure_default_template(path: Path) -> None:
    if path.exists():
        return
    doc = Document()
    doc.add_heading("投标文件", level=1)
    doc.add_paragraph("项目名称：{{project_name}}")
    doc.add_paragraph("技术方案：{{technical_plan}}")
    doc.add_paragraph("实施计划：{{implementation_plan}}")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)


def render_word(output_path: str, placeholders: dict[str, str], template_path: str | None = None) -> str:
    template_file = Path(template_path) if template_path else Path("templates/default_tender_template.docx")
    ensure_default_template(template_file)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    tpl = DocxTemplate(str(template_file))
    tpl.render(placeholders)
    tpl.save(str(out))
    return str(out)
