from __future__ import annotations

import copy
import re
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Iterable

from app.schemas.contracts import EvidenceUpsertItem
from app.services.expert_chunking import chunk_sections_for_rag
from app.services.expert_markdown import render_enhanced_markdown
from app.services.section_enhancement import enhance_section_metadata

_SECTION_TYPE_OPTIONS = [
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
]
_DISCIPLINE_OPTIONS = ["电气", "土建", "暖通", "给排水", "通信", "结构", "综合", "其他"]
_PROJECT_PHASE_OPTIONS = ["投标文件", "施工规范", "施工组织设计", "竣工资料", "通用规范"]
_TABLE_TYPE_OPTIONS = ["设备清单", "人员简历", "业绩", "进度计划", "技术参数对照", "报价", "制度流程", "其他"]
_REUSABILITY_OPTIONS = ["high", "medium", "low"]
_RISK_LEVEL_OPTIONS = ["high", "medium", "low", "none"]


def _attr(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _extract_numbering(title: str) -> str | None:
    match = re.match(r"^\s*(第[一二三四五六七八九十百0-9]+[章节条款])", title or "")
    if match:
        return match.group(1)
    return None


def _safe_rows(rows: list[list[str]]) -> list[list[str]]:
    normalized: list[list[str]] = []
    for row in rows:
        values = [str(cell).strip() for cell in row]
        if any(values):
            normalized.append(values)
    return normalized


def _parse_table_rows(raw: str) -> list[list[str]]:
    lines = [line.strip() for line in (raw or "").splitlines() if line.strip()]
    rows: list[list[str]] = []
    for line in lines:
        if "|" in line:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
        elif "\t" in line:
            cells = [cell.strip() for cell in line.split("\t")]
        else:
            cells = [cell.strip() for cell in re.split(r"\s{2,}", line) if cell.strip()]
            if len(cells) <= 1:
                cells = [line]
        if any(cells):
            rows.append(cells)
    return _safe_rows(rows)


def _section_type_cn(title: str, text: str) -> str:
    scope = f"{title}\n{text}"
    if re.search(r"报价|价格|金额|清单计价", scope):
        return "报价说明"
    if re.search(r"进度|工期|里程碑|节点计划", scope):
        return "进度计划"
    if re.search(r"安全|文明施工|应急", scope):
        return "安全文明施工"
    if re.search(r"质量|质保|检验", scope):
        return "质量保证"
    if re.search(r"施工组织|施工方案|工艺|资源配置", scope):
        return "施工组织"
    if re.search(r"资质|资格|证书", scope):
        return "资质文件"
    if re.search(r"业绩|案例|类似项目", scope):
        return "业绩材料"
    if re.search(r"合同|条款|偏差|响应|废标|否决|合规", scope):
        return "合同条款响应"
    if re.search(r"商务|投标函|服务承诺", scope):
        return "商务部分"
    if re.search(r"技术|参数|方案", scope):
        return "技术方案"
    return "其他"


def _discipline_cn(title: str, text: str) -> str:
    scope = f"{title}\n{text}"
    if re.search(r"电力|电气|变电|输电|配电", scope):
        return "电气"
    if re.search(r"土建|建筑|地基|混凝土|砌筑|路基", scope):
        return "土建"
    if re.search(r"暖通|空调|通风", scope):
        return "暖通"
    if re.search(r"给排水|管网|污水|供水", scope):
        return "给排水"
    if re.search(r"通信|信号|弱电|网络", scope):
        return "通信"
    if re.search(r"钢结构|结构设计|受力", scope):
        return "结构"
    return "综合"


def _project_phase_cn(title: str, text: str) -> str:
    scope = f"{title}\n{text}"
    if re.search(r"竣工|移交|归档资料", scope):
        return "竣工资料"
    if re.search(r"施工组织|施工方案", scope):
        return "施工组织设计"
    if re.search(r"施工规范|验收规范|国家标准", scope):
        return "施工规范"
    if re.search(r"通用规范|行业通则", scope):
        return "通用规范"
    return "投标文件"


def _contains_score(text: str) -> bool:
    return bool(re.search(r"评分|得分|分值|加分|扣分", text))


def _contains_compliance(text: str) -> bool:
    return bool(re.search(r"必须|应当|不得|否决|废标|强制|不响应", text))


def _risk_level(text: str, contains_compliance_items: bool, contains_score_items: bool) -> str:
    if contains_compliance_items and re.search(r"废标|否决|强制|不得", text):
        return "high"
    if contains_compliance_items:
        return "medium"
    if contains_score_items:
        return "low"
    return "none"


def _reusability(text: str, section_type: str) -> str:
    if re.search(r"本项目|本工程|本标段|具体地址|具体业主", text):
        return "low"
    if section_type in {"安全文明施工", "质量保证", "施工组织", "技术方案"}:
        return "high"
    return "medium"


def _keywords(text: str, fallback: Iterable[str]) -> list[str]:
    candidates = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", text)
    seen: set[str] = set()
    ordered: list[str] = []
    for item in [*candidates, *fallback]:
        token = str(item).strip()
        if len(token) < 2:
            continue
        if token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= 20:
            break
    while len(ordered) < 3:
        ordered.append(f"关键词{len(ordered) + 1}")
    return ordered[:20]


def _score_topics(text: str) -> list[str]:
    topics: list[str] = []
    for token in ("评分标准", "技术评分点", "工期得分", "业绩加分", "人员得分"):
        if token[:2] in text or token in text:
            topics.append(token)
    return topics[:10]


def _table_type(table_text: str) -> str:
    if re.search(r"姓名|职务|证书|年龄", table_text):
        return "人员简历"
    if re.search(r"设备|规格|型号|数量", table_text):
        return "设备清单"
    if re.search(r"业绩|合同金额|完工", table_text):
        return "业绩"
    if re.search(r"工期|进度|计划", table_text):
        return "进度计划"
    if re.search(r"参数|对照|指标", table_text):
        return "技术参数对照"
    if re.search(r"报价|金额|单价|总价", table_text):
        return "报价"
    if re.search(r"制度|流程|职责", table_text):
        return "制度流程"
    return "其他"


def _evidence_quotes(text: str, page: int) -> list[dict]:
    sentences = [item.strip() for item in re.split(r"[。；;\n]+", text) if item.strip()]
    quotes: list[dict] = []
    for sentence in sentences:
        if not re.search(r"评分|得分|分值|必须|否决|废标|响应|条款", sentence):
            continue
        quote = sentence[:80]
        quotes.append({"quote": quote, "page": page})
        if len(quotes) >= 3:
            break
    return quotes


def _section_text(section: dict) -> str:
    parts: list[str] = []
    for block in section.get("blocks", []):
        block_type = str(block.get("type", "")).lower()
        if block_type == "table":
            rows = ((block.get("table") or {}).get("rows") or [])
            for row in rows:
                parts.append(" | ".join(str(cell) for cell in row))
        else:
            parts.append(str(block.get("text", "") or ""))
    return "\n".join(item for item in parts if item.strip())


def build_structure_v1_from_blocks(
    *,
    doc_id: str,
    title: str | None,
    source_file: str,
    source_format: str,
    blocks: list[Any],
    parser_version: str,
    doc_type: str = "bid",
) -> dict:
    structure = {
        "doc_id": doc_id,
        "title": title or doc_id,
        "doc_type": doc_type if doc_type in {"bid", "spec", "manual", "other"} else "other",
        "source_file": source_file,
        "source_format": source_format if source_format in {"docx", "pdf", "scanned_pdf"} else "pdf",
        "parser_version": parser_version,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "sections": [],
    }
    sections: list[dict] = []
    current_anchor = ""
    current_section: dict | None = None
    text_idx = 0
    table_idx = 0
    section_idx = 0

    for block in blocks:
        raw_text = str(_attr(block, "content_text", "") or "").strip()
        if not raw_text:
            continue
        page = int(_attr(block, "page_no", 1) or 1)
        anchor = str(_attr(block, "section_anchor", "") or "").strip() or "未命名章节"
        if anchor != current_anchor or current_section is None:
            section_idx += 1
            current_anchor = anchor
            text_idx = 0
            table_idx = 0
            current_section = {
                "section_id": f"S{section_idx:03d}",
                "title": anchor,
                "level": 2,
                "page_start": page,
                "page_end": page,
                "numbering": _extract_numbering(anchor),
                "blocks": [],
            }
            sections.append(current_section)

        current_section["page_end"] = max(int(current_section["page_end"]), page)
        block_type = str(_attr(block, "block_type", "PARA") or "PARA").upper()
        if block_type == "TABLE":
            table_idx += 1
            table_id = f"{current_section['section_id']}.T{table_idx:03d}"
            rows = _parse_table_rows(raw_text)
            current_section["blocks"].append(
                {
                    "block_id": table_id,
                    "type": "table",
                    "page": page,
                    "table": {"table_id": table_id, "title": None, "continued": False, "rows": rows},
                }
            )
        else:
            text_idx += 1
            block_id = f"{current_section['section_id']}.B{text_idx:03d}"
            current_section["blocks"].append(
                {
                    "block_id": block_id,
                    "type": "text",
                    "page": page,
                    "text": raw_text,
                }
            )

    structure["sections"] = [section for section in sections if section.get("blocks")]
    if not structure["sections"]:
        structure["sections"] = [
            {
                "section_id": "S001",
                "title": "未识别章节",
                "level": 1,
                "page_start": 1,
                "page_end": 1,
                "numbering": None,
                "blocks": [{"block_id": "S001.B001", "type": "text", "page": 1, "text": "内容为空"}],
            }
        ]
    return structure


def summarize_tables_in_structure(structure: dict) -> list[dict]:
    summaries: list[dict] = []
    for section in structure.get("sections", []):
        for block in section.get("blocks", []):
            if str(block.get("type", "")).lower() != "table":
                continue
            table = block.get("table") or {}
            rows = _safe_rows(table.get("rows") or [])
            table_text = "\n".join(" | ".join(row) for row in rows)
            key_columns = rows[0][:12] if rows else ["列1"]
            summary = {
                "section_id": section.get("section_id"),
                "table_id": table.get("table_id") or block.get("block_id"),
                "table_title_guess": table.get("title") or section.get("title", ""),
                "table_type": _table_type(table_text),
                "key_columns": key_columns or ["列1"],
                "row_count_est": max(len(rows) - 1, 0),
                "notes": f"page={block.get('page')}",
                "page": int(block.get("page") or section.get("page_start") or 1),
            }
            if summary["table_type"] not in _TABLE_TYPE_OPTIONS:
                summary["table_type"] = "其他"
            summaries.append(summary)
    return summaries


def enrich_sections_v1(structure: dict, table_summaries: list[dict] | None = None) -> list[dict]:
    table_summaries = table_summaries or []
    table_by_section: dict[str, list[dict]] = {}
    for summary in table_summaries:
        sid = str(summary.get("section_id") or "")
        table_by_section.setdefault(sid, []).append(summary)

    metas: list[dict] = []
    for section in structure.get("sections", []):
        section_id = str(section.get("section_id", ""))
        title = str(section.get("title", ""))
        text = _section_text(section)
        base = enhance_section_metadata(section_id=section_id, section_title=title, section_text=text)
        table_scope = table_by_section.get(section_id, [])
        table_hint = " ".join(item.get("table_type", "") for item in table_scope)

        contains_score_items = _contains_score(f"{text}\n{table_hint}")
        contains_compliance_items = _contains_compliance(f"{text}\n{table_hint}")
        section_type = _section_type_cn(title, f"{text}\n{table_hint}")
        discipline = _discipline_cn(title, text)
        project_phase = _project_phase_cn(title, text)
        reusability = _reusability(text, section_type)
        if reusability not in _REUSABILITY_OPTIONS:
            reusability = "medium"
        compliance_risk_level = _risk_level(text, contains_compliance_items, contains_score_items)
        if compliance_risk_level not in _RISK_LEVEL_OPTIONS:
            compliance_risk_level = "none"
        summary = str(base.get("summary", "") or "").strip()
        if len(text.strip()) < 24:
            summary = f"{summary} 信息不足".strip()
        summary = summary[:600]
        confidence = float(base.get("confidence", 0.6) or 0.6)
        if len(text.strip()) < 24:
            confidence = min(confidence, 0.5)
        confidence = max(0.0, min(confidence, 1.0))
        keywords = _keywords(f"{title}\n{text}\n{table_hint}", [section_type, discipline, project_phase])
        score_related_topics = _score_topics(f"{text}\n{table_hint}") if contains_score_items else []

        meta = {
            "section_id": section_id,
            "section_title": title,
            "section_type": section_type if section_type in _SECTION_TYPE_OPTIONS else "其他",
            "discipline": discipline if discipline in _DISCIPLINE_OPTIONS else "其他",
            "project_phase": project_phase if project_phase in _PROJECT_PHASE_OPTIONS else "投标文件",
            "reusability": reusability,
            "contains_score_items": contains_score_items,
            "contains_compliance_items": contains_compliance_items,
            "score_related_topics": score_related_topics[:10],
            "compliance_risk_level": compliance_risk_level,
            "keywords": keywords,
            "summary": summary,
            "confidence": confidence,
        }
        metas.append(meta)
    return metas


def risk_review_sections(
    structure: dict,
    section_metas: list[dict],
    strong_review_confidence: float = 0.75,
) -> list[dict]:
    section_map = {str(section.get("section_id")): section for section in structure.get("sections", [])}
    reviews: list[dict] = []
    for meta in section_metas:
        confidence = float(meta.get("confidence", 0.0) or 0.0)
        contains_compliance_items = bool(meta.get("contains_compliance_items", False))
        contains_score_items = bool(meta.get("contains_score_items", False))
        compliance_risk_level = str(meta.get("compliance_risk_level", "none") or "none")
        needs_review = (
            contains_compliance_items
            or compliance_risk_level == "high"
            or (contains_score_items and confidence < strong_review_confidence)
        )
        if not needs_review:
            continue

        section_id = str(meta.get("section_id", ""))
        section = section_map.get(section_id, {})
        text = _section_text(section)
        page = int(section.get("page_start") or 1)
        quotes = _evidence_quotes(text, page)
        if compliance_risk_level == "high" and not quotes:
            excerpt = text.strip()[:80]
            if excerpt:
                quotes = [{"quote": excerpt, "page": page}]

        reason = "存在评分关键点或合规关键点，建议人工复核。"
        if not quotes:
            reason = "未找到明确句子，建议人工复核。"

        item = {
            "section_id": section_id,
            "is_score_critical": contains_score_items,
            "is_compliance_critical": contains_compliance_items or compliance_risk_level in {"high", "medium"},
            "compliance_risk_level": compliance_risk_level if compliance_risk_level in _RISK_LEVEL_OPTIONS else "none",
            "evidence_quotes": quotes[:3],
            "reason": reason[:400],
            "confidence": max(0.0, min(confidence + (0.08 if quotes else -0.2), 1.0)),
        }
        reviews.append(item)
    return reviews


def merge_structure_meta_risk(structure: dict, section_metas: list[dict], risk_reviews: list[dict]) -> dict:
    merged = copy.deepcopy(structure)
    merged["enhance_version"] = "v1"
    meta_map = {str(item.get("section_id", "")): item for item in section_metas}
    risk_map = {str(item.get("section_id", "")): item for item in risk_reviews}

    for section in merged.get("sections", []):
        section_id = str(section.get("section_id", ""))
        section["meta"] = meta_map.get(section_id, {})
        if section_id in risk_map:
            section["risk_review"] = risk_map[section_id]
    return merged


def build_exceptions_queue(
    *,
    doc_id: str,
    merged: dict,
    low_confidence: float,
    max_section_pages: int,
) -> list[dict]:
    exceptions: list[dict] = []
    for section in merged.get("sections", []):
        section_id = str(section.get("section_id", ""))
        page_start = int(section.get("page_start") or 1)
        page_end = int(section.get("page_end") or page_start)
        pages = max(1, page_end - page_start + 1)
        meta = section.get("meta", {}) or {}
        confidence = float(meta.get("confidence", 0.0) or 0.0)
        if confidence < low_confidence:
            exceptions.append(
                {
                    "doc_id": doc_id,
                    "section_id": section_id,
                    "issue": "LOW_CONFIDENCE",
                    "detail": f"confidence={confidence:.2f}",
                    "action": "HUMAN_REVIEW",
                }
            )
        if pages > max_section_pages:
            exceptions.append(
                {
                    "doc_id": doc_id,
                    "section_id": section_id,
                    "issue": "SECTION_TOO_LONG",
                    "detail": f"pages={pages}",
                    "action": "REPARSE_OR_SPLIT",
                }
            )
        for block in section.get("blocks", []):
            if str(block.get("type", "")).lower() != "table":
                continue
            table = block.get("table") or {}
            table_id = str(table.get("table_id") or block.get("block_id") or "")
            rows = _safe_rows(table.get("rows") or [])
            if not rows:
                exceptions.append(
                    {
                        "doc_id": doc_id,
                        "section_id": section_id,
                        "issue": "TABLE_EMPTY",
                        "detail": f"table_id={table_id}",
                        "action": "REEXTRACT_TABLE",
                    }
                )
    return exceptions


def _table_to_markdown(rows: list[list[str]]) -> str:
    safe_rows = _safe_rows(rows)
    if not safe_rows:
        return "| 空表 |\n| --- |\n|  |"
    header = safe_rows[0]
    body = safe_rows[1:] or [["" for _ in header]]
    line_header = f"| {' | '.join(header)} |"
    line_sep = f"| {' | '.join(['---'] * len(header))} |"
    line_body = [f"| {' | '.join(row[: len(header)] + [''] * max(0, len(header) - len(row)))} |" for row in body]
    return "\n".join([line_header, line_sep, *line_body])


def _to_markdown_doc(merged: dict) -> dict:
    sections: list[dict] = []
    for section in merged.get("sections", []):
        section_blocks: list[dict] = []
        for block in section.get("blocks", []):
            if str(block.get("type", "")).lower() == "table":
                table = block.get("table") or {}
                section_blocks.append(
                    {
                        "type": "table",
                        "page": int(block.get("page") or section.get("page_start") or 1),
                        "table_md": _table_to_markdown(_safe_rows(table.get("rows") or [])),
                    }
                )
            else:
                section_blocks.append(
                    {
                        "type": "text",
                        "page": int(block.get("page") or section.get("page_start") or 1),
                        "text": str(block.get("text", "") or ""),
                    }
                )
        meta = section.get("meta", {}) or {}
        sections.append(
            {
                "section_id": section.get("section_id"),
                "title": section.get("title"),
                "level": int(section.get("level") or 2),
                "page_start": int(section.get("page_start") or 1),
                "page_end": int(section.get("page_end") or 1),
                "meta": {
                    "section_type": meta.get("section_type", "其他"),
                    "discipline": meta.get("discipline", "其他"),
                    "project_phase": meta.get("project_phase", "投标文件"),
                    "reusability": meta.get("reusability", "medium"),
                    "contains_score_items": bool(meta.get("contains_score_items", False)),
                    "contains_compliance_items": bool(meta.get("contains_compliance_items", False)),
                    "compliance_risk_level": meta.get("compliance_risk_level", "none"),
                    "confidence": float(meta.get("confidence", 0.0) or 0.0),
                    "keywords": list(meta.get("keywords", [])),
                },
                "blocks": section_blocks,
            }
        )

    return {
        "doc_id": merged.get("doc_id"),
        "doc_type": merged.get("doc_type", "other"),
        "source_file": merged.get("source_file", ""),
        "source_format": merged.get("source_format", "pdf"),
        "parser_version": merged.get("parser_version", "v1"),
        "enhance_version": merged.get("enhance_version", "v1"),
        "created_at": merged.get("created_at", datetime.now().isoformat(timespec="seconds")),
        "title": merged.get("title"),
        "sections": sections,
    }


def render_enterprise_markdown(merged: dict) -> str:
    return render_enhanced_markdown(_to_markdown_doc(merged))


def _to_chunk_sections(merged: dict) -> list[dict]:
    return _to_markdown_doc(merged).get("sections", [])


def chunks_for_enterprise_rag(
    merged: dict,
    *,
    industry_tag: str | None,
    doc_type: str,
    min_tokens: int = 800,
    max_tokens: int = 1200,
    overlap_tokens: int = 120,
) -> list[EvidenceUpsertItem]:
    return chunk_sections_for_rag(
        doc_id=str(merged.get("doc_id", "")),
        sections=_to_chunk_sections(merged),
        industry_tag=industry_tag,
        doc_type=doc_type,
        min_tokens=min_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens,
    )


def serialize_chunks_jsonl(chunks: list[EvidenceUpsertItem]) -> list[dict]:
    records: list[dict] = []
    for chunk in chunks:
        locator = chunk.source_locator or {}
        metadata = {
            "doc_id": locator.get("doc_id"),
            "section_id": locator.get("section_id"),
            "section_type": locator.get("section_type"),
            "discipline": locator.get("discipline"),
            "source_page": locator.get("source_page"),
        }
        records.append(
            {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "metadata": metadata,
                "source_map": locator,
            }
        )
    return records


def to_namespace(value: Any) -> SimpleNamespace:
    if isinstance(value, SimpleNamespace):
        return value
    if isinstance(value, dict):
        return SimpleNamespace(**value)
    return SimpleNamespace(value=value)
