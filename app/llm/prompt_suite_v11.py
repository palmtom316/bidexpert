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

SECTION_TYPED_GUIDANCE = {
    "施工方案": {
        "structure_constraints": [
            "施工组织与资源配置",
            "关键工序与进度计划",
            "质量、安全与风险控制",
        ],
        "terminology": ["施工组织", "关键线路", "里程碑节点", "质量验收", "安全文明施工"],
    },
    "商务响应": {
        "structure_constraints": [
            "商务条款响应矩阵",
            "履约承诺与服务计划",
            "偏差说明与风险提示",
        ],
        "terminology": ["商务条款", "履约承诺", "服务响应", "偏差说明", "合同义务"],
    },
    "资审文件": {
        "structure_constraints": [
            "企业资质与许可证照",
            "项目经理与关键人员资格",
            "类似业绩与证明材料",
        ],
        "terminology": ["资格审查", "资质证书", "执业资格", "类似业绩", "资格否决"],
    },
    "评标响应": {
        "structure_constraints": [
            "评分项逐条响应",
            "加分项覆盖说明",
            "扣分风险规避措施",
        ],
        "terminology": ["评分办法", "加分项", "扣分项", "评审标准", "条款覆盖率"],
    },
}

DEFAULT_TYPED_GUIDANCE = {
    "structure_constraints": ["需求响应", "证据支撑", "风险说明"],
    "terminology": ["条款响应", "证据映射", "合规性", "一致性", "可追溯性"],
}


def _dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _typed_guidance(section_type: str | None) -> dict[str, list[str]]:
    normalized = (section_type or "").strip()
    return SECTION_TYPED_GUIDANCE.get(normalized, DEFAULT_TYPED_GUIDANCE)


def build_tender_parsing_prompt(tender_md: str) -> str:
    return (
        f"{GENERAL_RULES}\n\n"
        "你是招标规则拆解引擎。\n"
        "任务：抽取 mandatory_requirements、scoring_items、deliverables。\n"
        "解析时必须覆盖四类领域：资审、商务、技术、评标。\n"
        "必须显式提取废标条款、资格否决条款、扣分条款和加分条款。\n"
        "废标/资格否决与扣分条款必须分开标注，不得混淆。\n"
        "必须输出合法 JSON。\n"
        f"输入：\n{tender_md}\n"
    )


def build_global_facts_prompt(confirmed_data: str) -> str:
    target = {
        "project_name": "",
        "project_code": None,
        "construction_unit": None,
        "supervision_unit": None,
        "tenderer": None,
        "total_duration_days": None,
        "schedule_milestones": [],
        "quality_standard": None,
        "safety_civilization_level": None,
        "subcontracting_limit": None,
        "bid_bond_amount": None,
        "performance_bond_amount": None,
        "warranty_period_months": None,
        "project_manager": {"name": None, "certificate_no": None},
        "voltage_level": None,
        "contract_amount": None,
        "tax_rate": None,
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
    section_type: str | None = None,
) -> str:
    guidance = _typed_guidance(section_type)
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
        f"【章节类型】\n{section_type or '通用章节'}\n\n"
        f"【结构约束】\n{_dump(guidance['structure_constraints'])}\n\n"
        f"【术语词表】\n{_dump(guidance['terminology'])}\n\n"
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
    checklist = [
        "工期一致性",
        "证书一致性",
        "参数一致性",
        "废标条款覆盖率",
    ]
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
        f"章节类型：{section_type or '通用章节'}\n"
        f"必须逐项检查：{_dump(checklist)}\n"
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
