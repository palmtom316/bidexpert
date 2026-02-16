from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services.expert_enterprise_pipeline import (
    build_exceptions_queue,
    build_structure_v1_from_blocks,
    chunks_for_enterprise_rag,
    enrich_sections_v1,
    merge_structure_meta_risk,
    render_enterprise_markdown,
    risk_review_sections,
    serialize_chunks_jsonl,
    summarize_tables_in_structure,
)
from app.services.expert_workspace import ensure_expert_library_layout, sync_enterprise_config_assets


def test_sync_enterprise_config_assets_creates_required_files(tmp_path: Path) -> None:
    layout = ensure_expert_library_layout(tmp_path / "tender-expert-lib")
    sync_enterprise_config_assets(layout)

    required_files = [
        "00_config/enums/section_type.v1.yaml",
        "00_config/enums/discipline.v1.yaml",
        "00_config/enums/project_phase.v1.yaml",
        "00_config/enums/table_type.v1.yaml",
        "00_config/schema/structure.v1.schema.json",
        "00_config/schema/section_meta.v1.schema.json",
        "00_config/schema/risk_review.v1.schema.json",
        "00_config/schema/table_summary.v1.schema.json",
        "00_config/prompts/claude.section_meta.v1.txt",
        "00_config/prompts/claude.risk_review.v1.txt",
        "00_config/prompts/claude.table_summary.v1.txt",
        "00_config/prompts/claude.json_repair.v1.txt",
        "00_config/render/enhanced_document.md.j2",
        "00_config/render/chunk.md.j2",
        "00_config/pipeline/pipeline.v1.yaml",
        "00_config/pipeline/thresholds.v1.yaml",
    ]
    for rel in required_files:
        assert (layout.root / rel).is_file()

    structure_schema = json.loads((layout.root / "00_config/schema/structure.v1.schema.json").read_text())
    assert structure_schema["title"] == "DocumentStructureV1"
    assert "sections" in structure_schema["properties"]


def test_build_structure_enrich_risk_merge_and_exceptions() -> None:
    blocks = [
        SimpleNamespace(
            page_no=1,
            block_type="PARA",
            section_anchor="第一章 技术方案",
            content_text="投标人必须提供总体技术方案，并说明质量保证措施。",
        ),
        SimpleNamespace(
            page_no=2,
            block_type="TABLE",
            section_anchor="第一章 技术方案",
            content_text="项目 | 参数\n主变 | 2x50MVA",
        ),
        SimpleNamespace(
            page_no=3,
            block_type="PARA",
            section_anchor="第二章 合同条款响应",
            content_text="如不响应关键条款，将导致否决投标。",
        ),
    ]
    structure = build_structure_v1_from_blocks(
        doc_id="2023-xx项目",
        title="2023-xx项目",
        source_file="demo.pdf",
        source_format="pdf",
        blocks=blocks,
        parser_version="v1",
    )
    assert structure["doc_id"] == "2023-xx项目"
    assert len(structure["sections"]) == 2
    assert structure["sections"][0]["blocks"][1]["type"] == "table"

    table_summaries = summarize_tables_in_structure(structure)
    assert len(table_summaries) == 1
    assert table_summaries[0]["row_count_est"] >= 1

    metas = enrich_sections_v1(structure, table_summaries)
    assert len(metas) == 2
    assert all("section_id" in item for item in metas)

    # force one low-confidence section to test exception routing
    metas[0]["confidence"] = 0.5
    risks = risk_review_sections(structure, metas, strong_review_confidence=0.75)
    merged = merge_structure_meta_risk(structure, metas, risks)
    exceptions = build_exceptions_queue(
        doc_id=structure["doc_id"],
        merged=merged,
        low_confidence=0.6,
        max_section_pages=20,
    )
    assert any(item["issue"] == "LOW_CONFIDENCE" for item in exceptions)


def test_render_and_chunk_outputs_follow_enterprise_contract() -> None:
    long_text = " ".join(f"token{i}" for i in range(2100))
    structure = {
        "doc_id": "doc-enterprise-1",
        "title": "示例项目",
        "doc_type": "bid",
        "source_file": "demo.pdf",
        "source_format": "pdf",
        "parser_version": "v1",
        "created_at": "2026-02-16T13:00:14",
        "sections": [
            {
                "section_id": "S001",
                "title": "第一章 技术方案",
                "level": 2,
                "page_start": 1,
                "page_end": 3,
                "blocks": [
                    {"block_id": "S001.B001", "type": "text", "page": 1, "text": long_text},
                    {
                        "block_id": "S001.T001",
                        "type": "table",
                        "page": 3,
                        "table": {"table_id": "S001.T001", "rows": [["项目", "参数"], ["主变", "2x50MVA"]]},
                    },
                ],
            }
        ],
    }
    metas = enrich_sections_v1(structure, summarize_tables_in_structure(structure))
    merged = merge_structure_meta_risk(structure, metas, [])

    markdown = render_enterprise_markdown(merged)
    assert "# 示例项目" in markdown
    assert ":::metadata" in markdown

    chunks = chunks_for_enterprise_rag(
        merged,
        industry_tag="电力",
        doc_type="EXPERT_HISTORY",
        min_tokens=800,
        max_tokens=1200,
    )
    chunk_records = serialize_chunks_jsonl(chunks)
    assert chunk_records
    assert any(record["source_map"]["block_type"] == "table" for record in chunk_records)
    for record in chunk_records:
        assert "text" in record
        assert "metadata" in record
        assert "source_map" in record
        assert record["metadata"]["doc_id"] == "doc-enterprise-1"
