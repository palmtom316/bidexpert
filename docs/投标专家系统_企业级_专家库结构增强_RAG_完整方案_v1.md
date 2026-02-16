# 投标专家系统（企业级）——专家库自动结构增强 + RAG 入库 + 质量闸门（完整版）

生成时间：2026-02-16 13:00:14

> 适用规模：约 100 份历史投标文件 / 施工规范（可扩展到 1000+）  
> 目标：自动结构增强、metadata 标注、页码映射、RAG
> 分片、向量入库；人工仅复核异常队列。

------------------------------------------------------------------------

## 目录

1.  总体架构与产物  
2.  完整目录结构（企业级）  
3.  JSON Schema（完整版本）  
4.  Claude Prompts（主标注/风险复核/表格摘要/JSON 修复）  
5.  Pipeline 配置示例（YAML，可直接落地）  
6.  自动校验规则与异常队列  
7.  运行与验收建议（100 份规模）

------------------------------------------------------------------------

# 1. 总体架构与产物

**核心原则：**  
- **规则/解析器**做确定性结构（章节树、块、表格、页码映射）。  
- **AI**只做语义增强（分类、关键词、风险、复用价值），并且**只输出
JSON**。  
- **程序**渲染增强型 Markdown、做分片、做校验、做异常路由。

**每份文件最终落地 3 份关键资产：** 1. 原件存档：`01_raw/*.docx|pdf`  
2. 结构骨架：`02_extracted/structure.v1.json`  
3. 增强文档：`04_md/*.enhanced.md`（含 metadata 与页码映射）

------------------------------------------------------------------------

# 2. 完整目录结构（企业级）

> 把“配置/Schema/Prompt/渲染模板/运行日志/异常复核”全部标准化，确保可审计可复现。

``` text
tender-expert-lib/
  00_config/
    enums/
      section_type.v1.yaml
      discipline.v1.yaml
      project_phase.v1.yaml
      table_type.v1.yaml
    schema/
      structure.v1.schema.json
      section_meta.v1.schema.json
      risk_review.v1.schema.json
      table_summary.v1.schema.json
    prompts/
      claude.section_meta.v1.txt
      claude.risk_review.v1.txt
      claude.table_summary.v1.txt
      claude.json_repair.v1.txt
    render/
      enhanced_document.md.j2
      chunk.md.j2
    pipeline/
      pipeline.v1.yaml
      thresholds.v1.yaml

  01_raw/                      # 原始文件（只读存档）
    2023-xx项目/
      bid/
        xxx.docx
        xxx.pdf

  02_extracted/                # 解析产物（可重复生成）
    2023-xx项目/
      structure.v1.json
      blocks/
        S001.B001.txt
        S001.T001.json

  03_enriched/                 # AI 产物（可重复生成）
    2023-xx项目/
      section_meta.v1.jsonl     # 每行一个 section meta
      risk_review.v1.jsonl      # 仅高风险 section 复核结果
      merged.v1.json            # 合并结构+meta(+risk)

  04_md/                       # 增强型 Markdown（专家库主形态）
    2023-xx项目.enhanced.md

  05_chunks/                   # RAG 分片（可重复生成）
    2023-xx项目/
      chunks.v1.jsonl           # 每行一个 chunk（text + metadata + source_map）

  06_index/                    # 向量索引（可重建）
    qdrant/ 或 milvus/ 或 faiss/

  07_review/                   # 人工复核（只改这里）
    exceptions.queue.jsonl
    2023-xx项目.review.yaml

  99_logs/
    pipeline_runs/
      2026-02-16_run01.json
```

------------------------------------------------------------------------

# 3. JSON Schema（完整版本）

## 3.1 structure.v1.schema.json

``` json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schema/structure.v1.schema.json",
  "title": "DocumentStructureV1",
  "type": "object",
  "required": ["doc_id", "source_file", "source_format", "sections"],
  "properties": {
    "doc_id": { "type": "string" },
    "title": { "type": "string" },
    "doc_type": { "type": "string", "enum": ["bid", "spec", "manual", "other"] },
    "source_file": { "type": "string" },
    "source_format": { "type": "string", "enum": ["docx", "pdf", "scanned_pdf"] },
    "parser_version": { "type": "string" },
    "created_at": { "type": "string" },
    "sections": {
      "type": "array",
      "minItems": 1,
      "items": { "$ref": "#/$defs/Section" }
    }
  },
  "$defs": {
    "Section": {
      "type": "object",
      "required": ["section_id", "title", "level", "page_start", "page_end", "blocks"],
      "properties": {
        "section_id": { "type": "string" },
        "title": { "type": "string" },
        "level": { "type": "integer", "minimum": 1, "maximum": 6 },
        "page_start": { "type": "integer", "minimum": 1 },
        "page_end": { "type": "integer", "minimum": 1 },
        "numbering": { "type": "string" },
        "blocks": {
          "type": "array",
          "items": { "$ref": "#/$defs/Block" }
        }
      }
    },
    "Block": {
      "type": "object",
      "required": ["block_id", "type", "page"],
      "properties": {
        "block_id": { "type": "string" },
        "type": { "type": "string", "enum": ["text", "table", "figure"] },
        "page": { "type": "integer", "minimum": 1 },
        "text": { "type": "string" },
        "table": { "$ref": "#/$defs/Table" },
        "figure": { "$ref": "#/$defs/Figure" }
      },
      "allOf": [
        { "if": { "properties": { "type": { "const": "text" } } }, "then": { "required": ["text"] } },
        { "if": { "properties": { "type": { "const": "table" } } }, "then": { "required": ["table"] } },
        { "if": { "properties": { "type": { "const": "figure" } } }, "then": { "required": ["figure"] } }
      ]
    },
    "Table": {
      "type": "object",
      "required": ["table_id", "rows"],
      "properties": {
        "table_id": { "type": "string" },
        "title": { "type": "string" },
        "continued": { "type": "boolean", "default": false },
        "rows": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "string" }
          }
        }
      }
    },
    "Figure": {
      "type": "object",
      "required": ["asset_id"],
      "properties": {
        "asset_id": { "type": "string" },
        "title": { "type": "string" }
      }
    }
  }
}
```

## 3.2 section_meta.v1.schema.json（AI 主标注输出）

``` json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schema/section_meta.v1.schema.json",
  "title": "SectionMetaV1",
  "type": "object",
  "required": [
    "section_id","section_title","section_type","discipline","project_phase",
    "reusability","contains_score_items","contains_compliance_items",
    "score_related_topics","compliance_risk_level","keywords","summary","confidence"
  ],
  "properties": {
    "section_id": { "type": "string" },
    "section_title": { "type": "string" },
    "section_type": {
      "type": "string",
      "enum": ["技术方案","商务部分","资质文件","业绩材料","施工组织","安全文明施工","质量保证","进度计划","报价说明","合同条款响应","其他"]
    },
    "discipline": {
      "type": "string",
      "enum": ["电气","土建","暖通","给排水","通信","结构","综合","其他"]
    },
    "project_phase": {
      "type": "string",
      "enum": ["投标文件","施工规范","施工组织设计","竣工资料","通用规范"]
    },
    "reusability": { "type": "string", "enum": ["high","medium","low"] },
    "contains_score_items": { "type": "boolean" },
    "contains_compliance_items": { "type": "boolean" },
    "score_related_topics": { "type": "array", "items": { "type": "string" }, "maxItems": 10 },
    "compliance_risk_level": { "type": "string", "enum": ["high","medium","low","none"] },
    "keywords": { "type": "array", "minItems": 3, "maxItems": 20, "items": { "type": "string" } },
    "summary": { "type": "string", "maxLength": 600 },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  }
}
```

## 3.3 risk_review.v1.schema.json（高风险复核输出）

``` json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schema/risk_review.v1.schema.json",
  "title": "RiskReviewV1",
  "type": "object",
  "required": [
    "section_id","is_score_critical","is_compliance_critical",
    "compliance_risk_level","evidence_quotes","reason","confidence"
  ],
  "properties": {
    "section_id": { "type": "string" },
    "is_score_critical": { "type": "boolean" },
    "is_compliance_critical": { "type": "boolean" },
    "compliance_risk_level": { "type": "string", "enum": ["high","medium","low","none"] },
    "evidence_quotes": {
      "type": "array",
      "maxItems": 3,
      "items": {
        "type": "object",
        "required": ["quote","page"],
        "properties": {
          "quote": { "type": "string", "maxLength": 120 },
          "page": { "type": "integer", "minimum": 1 }
        }
      }
    },
    "reason": { "type": "string", "maxLength": 400 },
    "confidence": { "type": "number", "minimum": 0.0, "maximum": 1.0 }
  }
}
```

## 3.4 table_summary.v1.schema.json（表格摘要输出）

``` json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.com/schema/table_summary.v1.schema.json",
  "title": "TableSummaryV1",
  "type": "object",
  "required": ["table_title_guess","table_type","key_columns","row_count_est","notes"],
  "properties": {
    "table_title_guess": { "type": "string" },
    "table_type": {
      "type": "string",
      "enum": ["设备清单","人员简历","业绩","进度计划","技术参数对照","报价","制度流程","其他"]
    },
    "key_columns": { "type": "array", "minItems": 1, "maxItems": 12, "items": { "type": "string" } },
    "row_count_est": { "type": "integer", "minimum": 0 },
    "notes": { "type": "string", "maxLength": 500 }
  }
}
```

------------------------------------------------------------------------

# 4. Claude Prompts（主标注/风险复核/表格摘要/JSON 修复）

## 4.1 claude.section_meta.v1.txt

``` text
你是电力与建筑工程投标文件/施工规范的结构增强分析专家。

任务：对以下“单个章节（section）”做语义增强标注，并输出严格 JSON（只允许输出 JSON；不得输出解释性文字）。

你必须：
- 只依据输入文本判断，不得编造。
- 信息不足时在 summary 说明“不足”，并降低 confidence。
- keywords 选 5-15 个，尽量是可检索的工程术语。

字段枚举（必须从以下选择）：

section_type ∈
[技术方案, 商务部分, 资质文件, 业绩材料, 施工组织, 安全文明施工, 质量保证, 进度计划, 报价说明, 合同条款响应, 其他]

discipline ∈
[电气, 土建, 暖通, 给排水, 通信, 结构, 综合, 其他]

project_phase ∈
[投标文件, 施工规范, 施工组织设计, 竣工资料, 通用规范]

reusability ∈ [high, medium, low]
compliance_risk_level ∈ [high, medium, low, none]

判定规则（重要）：

contains_score_items = true 若章节涉及：
- 评分标准响应 / 技术评分点展开 / 工期与资源得分点
- 类似业绩与人员简历评分点
- 技术参数优势与对比（倾向得分点）

contains_compliance_items = true 若章节涉及：
- 必须满足 / 否则否决 / 废标 / 不响应即否决 / 强制性条款
- 合同实质性响应 / 偏差表 / 资格条件硬性要求

reusability = high 若：
- 内容为通用方法、制度、流程、模板段落
- 与具体项目专属数值/地名/单位绑定较少

输出 JSON 模板（不得新增字段）：

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

输入如下：

【section_id】
{{SECTION_ID}}

【章节标题】
{{TITLE}}

【页码范围】
{{PAGE_START}}-{{PAGE_END}}

【章节正文】
{{CONTENT}}

【表格摘要】
{{TABLE_SUMMARY}}
```

## 4.2 claude.risk_review.v1.txt

``` text
你是投标文件“评分点/合规废标点”复核专家。

任务：仅判断该章节是否属于“评分关键点”或“合规/废标关键点”，并给出简短依据。
只输出严格 JSON（不得输出解释性文字）。

输出 JSON（不得新增字段）：
{
  "section_id": "",
  "is_score_critical": false,
  "is_compliance_critical": false,
  "compliance_risk_level": "none",
  "evidence_quotes": [
    {"quote": "", "page": 0}
  ],
  "reason": "",
  "confidence": 0.00
}

规则：
- evidence_quotes 最多 3 条，每条 quote ≤ 80 字，必须来自原文。
- 如果无法找到原文直接依据，confidence 降低，并说明“未找到明确句子”。
- 若判断为 high，必须至少给出 1 条 evidence_quotes。

输入：
【section_id】{{SECTION_ID}}
【页码范围】{{PAGE_START}}-{{PAGE_END}}
【正文】{{CONTENT}}
```

## 4.3 claude.table_summary.v1.txt

``` text
你是工程投标文档表格摘要器。

任务：将输入的表格（二维数据或转写文本）生成一个短摘要，用于后续章节理解。
只输出 JSON。不得输出解释性文字。

输出：
{
  "table_title_guess": "",
  "table_type": "其他",
  "key_columns": [],
  "row_count_est": 0,
  "notes": ""
}

输入表格：
{{TABLE_RAW}}
```

## 4.4 claude.json_repair.v1.txt

``` text
你是 JSON 修复器。

任务：把“模型输出”修复成合法 JSON，且字段必须完全符合给定 schema。
只输出修复后的 JSON；不得输出其他文字。

约束：
- 不能新增字段、不能删除字段
- 布尔值必须是 true/false
- confidence 必须是 0-1 的数字

【schema】
{{SCHEMA_JSON}}

【model_output】
{{MODEL_OUTPUT}}
```

------------------------------------------------------------------------

# 5. Pipeline 配置示例（pipeline.v1.yaml）

``` yaml
version: v1
project: tender-expert-lib

paths:
  raw_root: 01_raw
  extracted_root: 02_extracted
  enriched_root: 03_enriched
  md_root: 04_md
  chunks_root: 05_chunks
  review_root: 07_review
  logs_root: 99_logs/pipeline_runs

models:
  claude_primary:
    provider: anthropic
    model: claude-3-5-haiku-latest
    temperature: 0.2
    max_output_tokens: 600
  claude_strong:
    provider: anthropic
    model: claude-3-5-sonnet-latest
    temperature: 0.2
    max_output_tokens: 700

thresholds:
  low_confidence: 0.60
  strong_review_confidence: 0.75
  max_section_pages: 20
  max_chunk_tokens: 1200
  chunk_overlap_tokens: 120

stages:
  - name: classify_files
    type: python
    entry: pipeline.classify_files
    inputs:
      - "{{paths.raw_root}}"
    outputs:
      - "{{paths.logs_root}}/file_manifest.json"

  - name: extract_structure
    type: python
    entry: pipeline.extract_structure
    inputs:
      - "{{paths.raw_root}}"
      - "{{paths.logs_root}}/file_manifest.json"
    outputs:
      - "{{paths.extracted_root}}/**/structure.v1.json"

  - name: summarize_tables
    type: llm_map
    model_ref: claude_primary
    prompt_ref: 00_config/prompts/claude.table_summary.v1.txt
    foreach: "tables_in_structure"
    inputs:
      - "{{paths.extracted_root}}/**/structure.v1.json"
    outputs:
      - "{{paths.enriched_root}}/**/table_summary.v1.jsonl"

  - name: enrich_sections
    type: llm_map
    model_ref: claude_primary
    prompt_ref: 00_config/prompts/claude.section_meta.v1.txt
    foreach: "sections_in_structure"
    inputs:
      - "{{paths.extracted_root}}/**/structure.v1.json"
      - "{{paths.enriched_root}}/**/table_summary.v1.jsonl"
    outputs:
      - "{{paths.enriched_root}}/**/section_meta.v1.jsonl"

  - name: risk_review
    type: llm_filter_map
    model_ref: claude_strong
    prompt_ref: 00_config/prompts/claude.risk_review.v1.txt
    filter:
      any:
        - "section_meta.contains_compliance_items == true"
        - "section_meta.compliance_risk_level == 'high'"
        - "section_meta.contains_score_items == true and section_meta.confidence < {{thresholds.strong_review_confidence}}"
    inputs:
      - "{{paths.enriched_root}}/**/section_meta.v1.jsonl"
      - "{{paths.extracted_root}}/**/structure.v1.json"
    outputs:
      - "{{paths.enriched_root}}/**/risk_review.v1.jsonl"

  - name: merge_and_validate
    type: python
    entry: pipeline.merge_and_validate
    inputs:
      - "{{paths.extracted_root}}/**/structure.v1.json"
      - "{{paths.enriched_root}}/**/section_meta.v1.jsonl"
      - "{{paths.enriched_root}}/**/risk_review.v1.jsonl"
      - "00_config/schema/*.json"
    outputs:
      - "{{paths.enriched_root}}/**/merged.v1.json"
      - "{{paths.review_root}}/exceptions.queue.jsonl"

  - name: render_markdown
    type: python
    entry: pipeline.render_markdown
    inputs:
      - "{{paths.enriched_root}}/**/merged.v1.json"
      - "00_config/render/enhanced_document.md.j2"
    outputs:
      - "{{paths.md_root}}/*.enhanced.md"

  - name: chunk_for_rag
    type: python
    entry: pipeline.chunk_for_rag
    inputs:
      - "{{paths.md_root}}/*.enhanced.md"
    outputs:
      - "{{paths.chunks_root}}/**/chunks.v1.jsonl"
```

------------------------------------------------------------------------

# 6. 自动校验与异常队列（建议格式）

``` json
{"doc_id":"2023-xx项目","section_id":"S012","issue":"LOW_CONFIDENCE","detail":"confidence=0.52","action":"HUMAN_REVIEW"}
{"doc_id":"2023-xx项目","section_id":"S003","issue":"SECTION_TOO_LONG","detail":"pages=45","action":"REPARSE_OR_SPLIT"}
{"doc_id":"2023-xx项目","section_id":"S021","issue":"TABLE_EMPTY","detail":"table_id=T004","action":"REEXTRACT_TABLE"}
```

------------------------------------------------------------------------

# 7. 100 份规模的验收建议

-   section_meta JSON 解析成功率 ≥ 98%
-   页码覆盖率（所有 section 都有 page_start/end）= 100%
-   exceptions 占比 ≤ 20%（首轮），迭代后 ≤ 10%
-   高风险章节（compliance_risk_level=high）抽检覆盖率 = 100%
