from __future__ import annotations

import json

from app.services.expert_markdown import ENHANCED_MARKDOWN_TEMPLATE
from app.services.section_enhancement import (
    CLAUDE_JSON_REPAIR_PROMPT,
    CLAUDE_RISK_REVIEW_PROMPT,
    CLAUDE_SECTION_ENHANCEMENT_PROMPT,
    CLAUDE_TABLE_SUMMARY_PROMPT,
)

SECTION_TYPE_ENUM = """version: v1
values:
  - 技术方案
  - 商务部分
  - 资质文件
  - 业绩材料
  - 施工组织
  - 安全文明施工
  - 质量保证
  - 进度计划
  - 报价说明
  - 合同条款响应
  - 其他
"""

DISCIPLINE_ENUM = """version: v1
values:
  - 电气
  - 土建
  - 暖通
  - 给排水
  - 通信
  - 结构
  - 综合
  - 其他
"""

PROJECT_PHASE_ENUM = """version: v1
values:
  - 投标文件
  - 施工规范
  - 施工组织设计
  - 竣工资料
  - 通用规范
"""

TABLE_TYPE_ENUM = """version: v1
values:
  - 设备清单
  - 人员简历
  - 业绩
  - 进度计划
  - 技术参数对照
  - 报价
  - 制度流程
  - 其他
"""

STRUCTURE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/schema/structure.v1.schema.json",
    "title": "DocumentStructureV1",
    "type": "object",
    "required": ["doc_id", "source_file", "source_format", "sections"],
    "properties": {
        "doc_id": {"type": "string"},
        "title": {"type": "string"},
        "doc_type": {"type": "string", "enum": ["bid", "spec", "manual", "other"]},
        "source_file": {"type": "string"},
        "source_format": {"type": "string", "enum": ["docx", "pdf", "scanned_pdf"]},
        "parser_version": {"type": "string"},
        "created_at": {"type": "string"},
        "sections": {
            "type": "array",
            "minItems": 1,
            "items": {"$ref": "#/$defs/Section"},
        },
    },
    "$defs": {
        "Section": {
            "type": "object",
            "required": ["section_id", "title", "level", "page_start", "page_end", "blocks"],
            "properties": {
                "section_id": {"type": "string"},
                "title": {"type": "string"},
                "level": {"type": "integer", "minimum": 1, "maximum": 6},
                "page_start": {"type": "integer", "minimum": 1},
                "page_end": {"type": "integer", "minimum": 1},
                "numbering": {"type": "string"},
                "blocks": {"type": "array", "items": {"$ref": "#/$defs/Block"}},
            },
        },
        "Block": {
            "type": "object",
            "required": ["block_id", "type", "page"],
            "properties": {
                "block_id": {"type": "string"},
                "type": {"type": "string", "enum": ["text", "table", "figure"]},
                "page": {"type": "integer", "minimum": 1},
                "text": {"type": "string"},
                "table": {"$ref": "#/$defs/Table"},
                "figure": {"$ref": "#/$defs/Figure"},
            },
            "allOf": [
                {"if": {"properties": {"type": {"const": "text"}}}, "then": {"required": ["text"]}},
                {"if": {"properties": {"type": {"const": "table"}}}, "then": {"required": ["table"]}},
                {"if": {"properties": {"type": {"const": "figure"}}}, "then": {"required": ["figure"]}},
            ],
        },
        "Table": {
            "type": "object",
            "required": ["table_id", "rows"],
            "properties": {
                "table_id": {"type": "string"},
                "title": {"type": "string"},
                "continued": {"type": "boolean", "default": False},
                "rows": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "Figure": {
            "type": "object",
            "required": ["asset_id"],
            "properties": {"asset_id": {"type": "string"}, "title": {"type": "string"}},
        },
    },
}

SECTION_META_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/schema/section_meta.v1.schema.json",
    "title": "SectionMetaV1",
    "type": "object",
    "required": [
        "section_id",
        "section_title",
        "section_type",
        "discipline",
        "project_phase",
        "reusability",
        "contains_score_items",
        "contains_compliance_items",
        "score_related_topics",
        "compliance_risk_level",
        "keywords",
        "summary",
        "confidence",
    ],
    "properties": {
        "section_id": {"type": "string"},
        "section_title": {"type": "string"},
        "section_type": {
            "type": "string",
            "enum": [
                "技术方案",
                "商务部分",
                "资质文件",
                "业绩材料",
                "施工组织",
                "安全文明施工",
                "质量保证",
                "进度计划",
                "报价说明",
                "合同条款响应",
                "其他",
            ],
        },
        "discipline": {"type": "string", "enum": ["电气", "土建", "暖通", "给排水", "通信", "结构", "综合", "其他"]},
        "project_phase": {
            "type": "string",
            "enum": ["投标文件", "施工规范", "施工组织设计", "竣工资料", "通用规范"],
        },
        "reusability": {"type": "string", "enum": ["high", "medium", "low"]},
        "contains_score_items": {"type": "boolean"},
        "contains_compliance_items": {"type": "boolean"},
        "score_related_topics": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "compliance_risk_level": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "keywords": {
            "type": "array",
            "minItems": 3,
            "maxItems": 20,
            "items": {"type": "string"},
        },
        "summary": {"type": "string", "maxLength": 600},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}

RISK_REVIEW_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/schema/risk_review.v1.schema.json",
    "title": "RiskReviewV1",
    "type": "object",
    "required": [
        "section_id",
        "is_score_critical",
        "is_compliance_critical",
        "compliance_risk_level",
        "evidence_quotes",
        "reason",
        "confidence",
    ],
    "properties": {
        "section_id": {"type": "string"},
        "is_score_critical": {"type": "boolean"},
        "is_compliance_critical": {"type": "boolean"},
        "compliance_risk_level": {"type": "string", "enum": ["high", "medium", "low", "none"]},
        "evidence_quotes": {
            "type": "array",
            "maxItems": 3,
            "items": {
                "type": "object",
                "required": ["quote", "page"],
                "properties": {
                    "quote": {"type": "string", "maxLength": 120},
                    "page": {"type": "integer", "minimum": 1},
                },
            },
        },
        "reason": {"type": "string", "maxLength": 400},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
}

TABLE_SUMMARY_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/schema/table_summary.v1.schema.json",
    "title": "TableSummaryV1",
    "type": "object",
    "required": ["table_title_guess", "table_type", "key_columns", "row_count_est", "notes"],
    "properties": {
        "table_title_guess": {"type": "string"},
        "table_type": {
            "type": "string",
            "enum": ["设备清单", "人员简历", "业绩", "进度计划", "技术参数对照", "报价", "制度流程", "其他"],
        },
        "key_columns": {
            "type": "array",
            "minItems": 1,
            "maxItems": 12,
            "items": {"type": "string"},
        },
        "row_count_est": {"type": "integer", "minimum": 0},
        "notes": {"type": "string", "maxLength": 500},
    },
}

PIPELINE_CONFIG_YAML = """version: v1
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
  - name: extract_structure
    type: python
    entry: pipeline.extract_structure
  - name: summarize_tables
    type: llm_map
    model_ref: claude_primary
    prompt_ref: 00_config/prompts/claude.table_summary.v1.txt
  - name: enrich_sections
    type: llm_map
    model_ref: claude_primary
    prompt_ref: 00_config/prompts/claude.section_meta.v1.txt
  - name: risk_review
    type: llm_filter_map
    model_ref: claude_strong
    prompt_ref: 00_config/prompts/claude.risk_review.v1.txt
  - name: merge_and_validate
    type: python
    entry: pipeline.merge_and_validate
  - name: render_markdown
    type: python
    entry: pipeline.render_markdown
  - name: chunk_for_rag
    type: python
    entry: pipeline.chunk_for_rag
"""

THRESHOLDS_YAML = """low_confidence: 0.60
strong_review_confidence: 0.75
max_section_pages: 20
max_chunk_tokens: 1200
chunk_overlap_tokens: 120
"""

CHUNK_RENDER_TEMPLATE = """## Chunk {{ chunk.chunk_id }}
[source_page: {{ chunk.source_page }}]

{{ chunk.text }}
"""


def enterprise_default_files() -> dict[str, str]:
    return {
        "00_config/enums/section_type.v1.yaml": SECTION_TYPE_ENUM,
        "00_config/enums/discipline.v1.yaml": DISCIPLINE_ENUM,
        "00_config/enums/project_phase.v1.yaml": PROJECT_PHASE_ENUM,
        "00_config/enums/table_type.v1.yaml": TABLE_TYPE_ENUM,
        "00_config/schema/structure.v1.schema.json": json.dumps(STRUCTURE_SCHEMA, ensure_ascii=False, indent=2),
        "00_config/schema/section_meta.v1.schema.json": json.dumps(SECTION_META_SCHEMA, ensure_ascii=False, indent=2),
        "00_config/schema/risk_review.v1.schema.json": json.dumps(RISK_REVIEW_SCHEMA, ensure_ascii=False, indent=2),
        "00_config/schema/table_summary.v1.schema.json": json.dumps(TABLE_SUMMARY_SCHEMA, ensure_ascii=False, indent=2),
        "00_config/prompts/claude.section_meta.v1.txt": CLAUDE_SECTION_ENHANCEMENT_PROMPT,
        "00_config/prompts/claude.risk_review.v1.txt": CLAUDE_RISK_REVIEW_PROMPT,
        "00_config/prompts/claude.table_summary.v1.txt": CLAUDE_TABLE_SUMMARY_PROMPT,
        "00_config/prompts/claude.json_repair.v1.txt": CLAUDE_JSON_REPAIR_PROMPT,
        "00_config/render/enhanced_document.md.j2": ENHANCED_MARKDOWN_TEMPLATE,
        "00_config/render/chunk.md.j2": CHUNK_RENDER_TEMPLATE,
        "00_config/pipeline/pipeline.v1.yaml": PIPELINE_CONFIG_YAML,
        "00_config/pipeline/thresholds.v1.yaml": THRESHOLDS_YAML,
    }
