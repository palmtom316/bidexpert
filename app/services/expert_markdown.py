from __future__ import annotations

from jinja2 import Template

ENHANCED_MARKDOWN_TEMPLATE = """---
doc_id: {{ doc.doc_id }}
doc_type: {{ doc.doc_type }}
source_file: {{ doc.source_file }}
source_format: {{ doc.source_format }}
parser_version: {{ doc.parser_version }}
enhance_version: {{ doc.enhance_version }}
created_at: {{ doc.created_at }}
---

# {{ doc.title or doc.doc_id }}

{% for s in doc.sections %}
{{ "#" * s.level }} {{ s.title }}
[source_page: {{ s.page_start }}-{{ s.page_end }}]

:::metadata
section_id: {{ s.section_id }}
section_type: {{ s.meta.section_type }}
discipline: {{ s.meta.discipline }}
project_phase: {{ s.meta.project_phase }}
reusability: {{ s.meta.reusability }}
contains_score_items: {{ "true" if s.meta.contains_score_items else "false" }}
contains_compliance_items: {{ "true" if s.meta.contains_compliance_items else "false" }}
compliance_risk_level: {{ s.meta.compliance_risk_level }}
confidence: {{ s.meta.confidence }}
keywords: {{ s.meta.keywords }}
:::

{% for b in s.blocks %}
{% if b.type == "text" %}
[source_page: {{ b.page }}]
{{ b.text }}

{% elif b.type == "table" %}
### TABLE
[source_page: {{ b.page }}]
{{ b.table_md }}

{% endif %}
{% endfor %}

---
{% endfor %}
"""


def render_enhanced_markdown(doc: dict, template: str = ENHANCED_MARKDOWN_TEMPLATE) -> str:
    compiled = Template(template, trim_blocks=True, lstrip_blocks=True, autoescape=False)
    rendered = compiled.render(doc=doc)
    return f"{rendered.rstrip()}\n"
