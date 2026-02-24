from __future__ import annotations

import json
from typing import Any

GENERAL_RULES = """你是结构化投标生成引擎。

必须遵守：
1. 只输出合法 JSON。
2. 不允许输出 JSON 以外的任何文本。
3. 若信息不足，填 null，不允许编造。
4. 所有关键陈述必须附带 evidence。
5. 不得与 Global Facts 冲突。
6. 不得使用宣传性或夸大承诺语言。"""

CLAUDE_PROMPT_TEMPERATURE = {
    "tender_parsing": 0.1,
    "global_facts": 0.0,
    "consistency_extract": 0.0,
    "section_generate": 0.4,
    "review": 0.1,
    "repair": 0.25,
}


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_tender_parsing_prompt(tender_md: str) -> str:
    return (
        f"{GENERAL_RULES}\n\n"
        "你是招标规则拆解引擎。\n"
        "任务：抽取 mandatory_requirements、scoring_items、deliverables。\n\n"
        "解析指引：\n"
        "- 资格审查条款：识别资质要求、证书要求、业绩门槛等资审条件\n"
        "- 商务条款：识别报价要求、付款条件、合同条款、保证金等商务条件\n"
        "- 技术条款：识别技术参数、方案要求、工艺标准等技术条件\n"
        "- 评标评分规则：识别评分标准、权重分配、评标方法等评分条件\n"
        "- 废标与否决条款：识别废标条件、否决投标情形、取消资格条件\n\n"
        "必须输出合法 JSON。\n"
        f"输入：\n{tender_md}\n"
    )


def build_global_facts_prompt(confirmed_data: str) -> str:
    target = {
        "project_name": "",
        "total_duration_days": None,
        "project_manager": {"name": None, "certificate_no": None},
        "voltage_level": None,
        "contract_amount": None,
    }
    return (
        f"{GENERAL_RULES}\n\n"
        "你是全局事实提取引擎。\n"
        "只输出 JSON：\n"
        f"{_dump(target)}\n"
        f"输入：\n{confirmed_data}\n"
    )


def build_section_generation_prompt(
    *,
    global_facts_json: dict,
    relevant_requirements: list[str],
    relevant_scoring: list[str],
    top_chunks: list[dict],
) -> str:
    target = {
        "section_path": "",
        "content": "",
        "covers_req": [],
        "targets_score": [],
        "evidence": [
            {
                "doc_id": "",
                "page_range": {"start_page": 0, "end_page": 0},
                "chunk_id": "",
            }
        ],
        "assumptions": [],
        "risk_flags": [],
    }
    return (
        f"{GENERAL_RULES}\n\n"
        "你是结构化投标生成引擎。\n\n"
        f"【Global Facts】\n{_dump(global_facts_json)}\n\n"
        f"【招标规则子集】\n{_dump(relevant_requirements)}\n\n"
        f"【评分项子集】\n{_dump(relevant_scoring)}\n\n"
        f"【Rerank 后检索证据（含 parent_context）】\n{_dump(top_chunks)}\n\n"
        "输出 JSON：\n"
        f"{_dump(target)}"
    )


def build_consistency_extract_prompt(document_text: str) -> str:
    target = {
        "total_duration_days": None,
        "project_manager_name": None,
        "certificate_no": None,
        "voltage_level": None,
    }
    return (
        f"{GENERAL_RULES}\n\n"
        "一致性抽取任务。\n"
        f"提取字段：{_dump(target)}\n"
        f"输入：\n{document_text}"
    )


def build_review_prompt(generated_section_json: dict) -> str:
    target = {
        "issues": [
            {
                "severity": "high|medium|low",
                "type": "",
                "location": "",
                "desc": "",
                "suggest_fix": "",
            }
        ],
        "overall_risk": "low|medium|high",
    }
    return (
        f"{GENERAL_RULES}\n\n"
        "审稿任务：只输出 JSON。\n"
        f"目标结构：{_dump(target)}\n"
        f"输入：\n{_dump(generated_section_json)}"
    )


def build_fix_prompt(issues_json: dict, original_section_json: dict) -> str:
    return (
        f"{GENERAL_RULES}\n\n"
        "根据 issues 修复章节。\n"
        "保持 JSON 结构不变，不得修改 Global Facts。\n"
        f"输入 issues：\n{_dump(issues_json)}\n"
        f"输入 original：\n{_dump(original_section_json)}"
    )
