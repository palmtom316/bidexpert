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


from docx.shared import Cm

def render_word(output_path: str, placeholders: dict[str, str], template_path: str | None = None, style_config: dict | None = None) -> str:
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

    # 1. Render content using docxtpl
    tpl = DocxTemplate(str(template_file))
    tpl.render(placeholders)
    tpl.save(str(out))

    # 2. Apply Page Layout Styles using python-docx
    if style_config:
        doc = Document(str(out))
        page_cfg = style_config.get("page", {})
        
        # Apply margins to all sections
        if page_cfg:
            for section in doc.sections:
                if "marginTop" in page_cfg:
                    section.top_margin = Cm(float(page_cfg["marginTop"]))
                if "marginBottom" in page_cfg:
                    section.bottom_margin = Cm(float(page_cfg["marginBottom"]))
                if "marginLeft" in page_cfg:
                    section.left_margin = Cm(float(page_cfg["marginLeft"]))
                if "marginRight" in page_cfg:
                    section.right_margin = Cm(float(page_cfg["marginRight"]))
                
                # Header/Footer distance
                if "headerOffset" in page_cfg:
                    section.header_distance = Cm(float(page_cfg["headerOffset"]))
                if "footerOffset" in page_cfg:
                    section.footer_distance = Cm(float(page_cfg["footerOffset"]))

        # 3. Generate TOC if requested
        if style_config.get("generateTOC"):
            add_toc(doc)
            set_update_fields(doc)

        doc.save(str(out))

    return str(out)


from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def add_toc(doc):
    """
    Insert a Table of Contents (TOC) field code at the beginning of the document (or after cover).
    Field code: {TOC \o "1-3" \h \z \u}
    """
    paragraph = doc.add_paragraph()
    # Insert at the beginning (index 0)
    # doc.paragraphs.insert(0, paragraph) 
    # But doc.paragraphs is not a list you can insert into directly in python-docx API easily without moving elements.
    # The 'add_paragraph' appends to the end.
    # To insert at start:
    doc.element.body.insert(0, paragraph._element)
    
    run = paragraph.add_run()
    
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = r'TOC \o "1-3" \h \z \u'
    
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'separate')
    
    fldChar3 = OxmlElement('w:fldChar')
    fldChar3.set(qn('w:fldCharType'), 'end')
    
    run._r.append(fldChar1)
    run._r.append(instrText)
    run._r.append(fldChar2)
    run._r.append(fldChar3)

def set_update_fields(doc):
    """
    Set the document to update fields (like TOC) on opening.
    """
    settings = doc.settings.element
    updateFields = OxmlElement('w:updateFields')
    updateFields.set(qn('w:val'), 'true')
    settings.append(updateFields)


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
