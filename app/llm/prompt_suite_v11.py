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
        "project_location": None,
        "construction_unit": None,
        "supervision_unit": None,
        "design_unit": None,
        "total_duration_days": None,
        "project_manager": {"name": None, "certificate_no": None},
        "voltage_level": None,
        "contract_amount": None,
        "quality_standard": None,
        "safety_level": None,
        "subcontract_restriction": None,
        "milestone_nodes": None,
        "bid_bond_amount": None,
        "performance_bond_ratio": None,
    }
    return (
        f"{GENERAL_RULES}\n\n"
        "你是全局事实提取引擎。\n"
        "只输出 JSON：\n"
        f"{_dump(target)}\n"
        f"输入：\n{confirmed_data}\n"
    )


_SECTION_GENERATION_GUIDANCE: dict[str, str] = {
    "construction_plan": (
        "【章节约束：施工组织设计】\n"
        "- 必须包含：施工部署、施工进度计划、主要施工方法、工期保证措施\n"
        "- 工期数据必须与 Global Facts 中 total_duration_days 一致\n"
        "- 关键节点须与 milestone_nodes 对齐\n"
    ),
    "technical_proposal": (
        "【章节约束：技术方案】\n"
        "- 必须包含：技术路线、关键技术措施、技术参数响应、技术保障\n"
        "- 技术参数须逐项响应招标要求，不得遗漏\n"
        "- 引用的技术标准须为现行有效版本\n"
    ),
    "safety_plan": (
        "【章节约束：安全生产方案】\n"
        "- 必须包含：安全管理目标、安全组织机构、安全技术措施、应急预案\n"
        "- 安全等级须与 Global Facts 中 safety_level 一致\n"
        "- 须覆盖各工序安全风险点\n"
    ),
    "quality_plan": (
        "【章节约束：质量保证方案】\n"
        "- 必须包含：质量目标、质量管理体系、质量控制措施、质量检验计划\n"
        "- 质量标准须与 Global Facts 中 quality_standard 一致\n"
        "- 须明确检验批划分与验收标准\n"
    ),
    "schedule_plan": (
        "【章节约束：施工进度计划】\n"
        "- 必须包含：总进度计划、阶段进度、关键线路、工期保证措施\n"
        "- 总工期须与 Global Facts 中 total_duration_days 一致\n"
    ),
    "environmental_plan": (
        "【章节约束：环境保护方案】\n"
        "- 必须包含：环保目标、污染防治措施、水土保持、噪声控制\n"
    ),
    "resource_plan": (
        "【章节约束：资源配置方案】\n"
        "- 必须包含：人员配置、机械设备、材料供应计划\n"
    ),
    "commercial_proposal": (
        "【章节约束：商务方案】\n"
        "- 必须包含：报价说明、付款计划、合同条款响应\n"
        "- 金额须与 Global Facts 中 contract_amount 一致\n"
    ),
}

_REVIEW_CHECKLIST: dict[str, str] = {
    "construction_plan": (
        "审查要点：\n"
        "1. 工期一致性：施工进度是否与 Global Facts 工期吻合\n"
        "2. 证书一致性：项目经理资质是否与 Global Facts 一致\n"
        "3. 废标条款覆盖：是否遗漏招标文件中的废标/否决条件\n"
        "4. 参数一致性：技术参数是否与招标要求逐项对应\n"
    ),
    "technical_proposal": (
        "审查要点：\n"
        "1. 技术参数响应：是否逐项响应招标技术要求\n"
        "2. 标准有效性：引用的技术标准是否为现行版本\n"
        "3. 废标条款覆盖：是否遗漏技术类废标条件\n"
        "4. 一致性：技术方案与施工组织设计是否矛盾\n"
    ),
    "safety_plan": (
        "审查要点：\n"
        "1. 安全等级一致性：安全目标是否与招标要求一致\n"
        "2. 风险覆盖：是否覆盖各工序安全风险点\n"
        "3. 废标条款覆盖：是否遗漏安全类否决条件\n"
        "4. 应急预案完整性：是否包含必要的应急响应流程\n"
    ),
    "quality_plan": (
        "审查要点：\n"
        "1. 质量标准一致性：质量目标是否与招标要求一致\n"
        "2. 检验计划完整性：检验批划分是否合理\n"
        "3. 废标条款覆盖：是否遗漏质量类否决条件\n"
        "4. 参数一致性：质量指标是否与技术方案一致\n"
    ),
}

_DEFAULT_REVIEW_CHECKLIST = (
    "审查要点：\n"
    "1. 一致性：内容是否与 Global Facts 一致\n"
    "2. 废标条款覆盖：是否遗漏招标文件中的废标/否决条件\n"
    "3. 参数一致性：关键参数是否与招标要求对应\n"
)


def build_section_generation_prompt(
    *,
    global_facts_json: dict,
    relevant_requirements: list[str],
    relevant_scoring: list[str],
    top_chunks: list[dict],
    section_type: str | None = None,
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
    section_guidance = ""
    if section_type and section_type in _SECTION_GENERATION_GUIDANCE:
        section_guidance = f"\n{_SECTION_GENERATION_GUIDANCE[section_type]}\n"

    return (
        f"{GENERAL_RULES}\n\n"
        "你是结构化投标生成引擎。\n\n"
        f"{section_guidance}"
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


def build_review_prompt(generated_section_json: dict, *, section_type: str | None = None) -> str:
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
    checklist = ""
    if section_type:
        checklist = _REVIEW_CHECKLIST.get(section_type, _DEFAULT_REVIEW_CHECKLIST)
        checklist = f"\n{checklist}\n"

    return (
        f"{GENERAL_RULES}\n\n"
        "审稿任务：只输出 JSON。\n"
        f"{checklist}"
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
