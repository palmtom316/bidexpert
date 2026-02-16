from __future__ import annotations

import re

from app.services.expert_chunking import chunk_sections_for_rag
from app.services.expert_costing import estimate_knowledge_enhancement_cost
from app.services.expert_markdown import render_enhanced_markdown
from app.services.expert_workspace import EXPERT_LIBRARY_STAGE_DIRS, ensure_expert_library_layout
from app.services.section_enhancement import CLAUDE_SECTION_ENHANCEMENT_PROMPT


def _token_count(text: str) -> int:
    return len(re.findall(r"[\w\u4e00-\u9fff]+", text))


def test_ensure_library_layout_creates_required_directories(tmp_path) -> None:
    layout = ensure_expert_library_layout(tmp_path / "tender-expert-lib")
    assert layout.root.name == "tender-expert-lib"
    for stage in EXPERT_LIBRARY_STAGE_DIRS:
        assert (layout.root / stage).is_dir()


def test_render_enhanced_markdown_contains_required_fields() -> None:
    doc = {
        "doc_id": "doc-001",
        "doc_type": "EXPERT_HISTORY",
        "source_file": "demo.pdf",
        "source_format": "pdf",
        "parser_version": "v1",
        "enhance_version": "v1",
        "created_at": "2026-02-16T12:48:01",
        "title": "示例专家知识",
        "sections": [
            {
                "section_id": "sec-001",
                "title": "第一章 总则",
                "level": 2,
                "page_start": 1,
                "page_end": 2,
                "meta": {
                    "section_type": "GENERAL",
                    "discipline": "ELECTRICAL",
                    "project_phase": "BIDDING",
                    "reusability": "HIGH",
                    "contains_score_items": True,
                    "contains_compliance_items": True,
                    "compliance_risk_level": "MEDIUM",
                    "confidence": 0.86,
                    "keywords": ["资质", "电力"],
                },
                "blocks": [
                    {"type": "text", "page": 1, "text": "投标人应具备相关资质。"},
                    {"type": "table", "page": 2, "table_md": "| 项目 | 要求 |"},
                ],
            }
        ],
    }
    rendered = render_enhanced_markdown(doc)
    assert "doc_id: doc-001" in rendered
    assert "# 示例专家知识" in rendered
    assert "## 第一章 总则" in rendered
    assert "[source_page: 1-2]" in rendered
    assert "section_id: sec-001" in rendered
    assert "discipline: ELECTRICAL" in rendered
    assert "contains_score_items: true" in rendered
    assert "contains_compliance_items: true" in rendered
    assert "### TABLE" in rendered
    assert "| 项目 | 要求 |" in rendered


def test_chunking_section_first_table_separate_and_required_metadata() -> None:
    long_text = " ".join(f"t{i}" for i in range(2200))
    sections = [
        {
            "section_id": "sec-001",
            "title": "第一章 技术方案",
            "level": 2,
            "page_start": 1,
            "page_end": 3,
            "meta": {
                "section_type": "TECHNICAL",
                "discipline": "ELECTRICAL",
                "project_phase": "CONSTRUCTION",
                "reusability": "HIGH",
                "contains_score_items": False,
                "contains_compliance_items": True,
                "compliance_risk_level": "LOW",
                "confidence": 0.9,
                "keywords": ["方案"],
            },
            "blocks": [
                {"type": "text", "page": 1, "text": long_text},
                {"type": "table", "page": 3, "table_md": "| 项目 | 参数 |"},
            ],
        }
    ]

    chunks = chunk_sections_for_rag(
        doc_id="doc-001",
        sections=sections,
        industry_tag="power",
        doc_type="EXPERT_HISTORY",
    )
    assert chunks

    text_chunks = [c for c in chunks if (c.source_locator or {}).get("block_type") == "text"]
    table_chunks = [c for c in chunks if (c.source_locator or {}).get("block_type") == "table"]
    assert len(table_chunks) == 1
    assert len(text_chunks) >= 2

    for chunk in text_chunks[:-1]:
        assert 800 <= _token_count(chunk.text) <= 1200

    for chunk in chunks:
        locator = chunk.source_locator or {}
        assert locator["doc_id"] == "doc-001"
        assert locator["section_id"] == "sec-001"
        assert locator["section_type"] == "TECHNICAL"
        assert locator["discipline"] == "ELECTRICAL"
        assert "source_page" in locator


def test_cost_estimate_and_prompt_follow_spec() -> None:
    estimate = estimate_knowledge_enhancement_cost(100)
    assert estimate["document_count"] == 100
    assert estimate["claude_enhancement_usd"] == {"min": 10.0, "max": 35.0}
    assert estimate["embedding_usd"] == {"max": 1.0}

    assert "你是电力与建筑工程投标文件/施工规范的结构增强分析专家。" in CLAUDE_SECTION_ENHANCEMENT_PROMPT
    assert "并输出严格 JSON" in CLAUDE_SECTION_ENHANCEMENT_PROMPT
    for key in [
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
    ]:
        assert f'"{key}"' in CLAUDE_SECTION_ENHANCEMENT_PROMPT
