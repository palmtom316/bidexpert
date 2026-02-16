# 投标专家系统 —— 专家库结构增强与RAG设计完整方案

生成时间：2026-02-16 12:48:01

------------------------------------------------------------------------

# 一、增强型 Markdown 渲染模板

## 文档级模板（示例）

``` jinja2
---
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
```

------------------------------------------------------------------------

# 二、专家库目录结构

    tender-expert-lib/
      00_config/
      01_raw/
      02_extracted/
      03_enriched/
      04_md/
      05_chunks/
      06_index/
      07_review/
      99_logs/

------------------------------------------------------------------------

# 三、RAG 分片策略

-   优先按章节切分
-   正文 chunk 800–1200 tokens
-   表格单独成块
-   chunk 必带
    metadata：doc_id、section_id、section_type、discipline、source_page

------------------------------------------------------------------------

# 四、100 份文件成本估算

-   Claude 增强阶段：约 10–35 美元
-   Embedding 阶段：约 1 美元以内

------------------------------------------------------------------------

# 五、Claude Section 增强 Prompt

``` text
你是电力与建筑工程投标文件结构增强专家。

任务：对单个章节进行语义增强标注。

输出必须为严格 JSON：

{
  "section_id": "",
  "section_title": "",
  "section_type": "",
  "discipline": "",
  "project_phase": "",
  "reusability": "",
  "contains_score_items": false,
  "contains_compliance_items": false,
  "score_related_topics": [],
  "compliance_risk_level": "",
  "keywords": [],
  "summary": "",
  "confidence": 0.00
}

禁止输出解释性文字。
```
