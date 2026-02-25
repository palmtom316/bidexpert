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
        "rated_capacity": None,
        "line_length": None,
        "conductor_type": None,
        "tower_count": None,
        "substation_type": None,
        "commissioning_deadline": None,
        "grid_connection_point": None,
        "seismic_fortification": None,
        "pollution_level": None,
        "altitude": None,
        "design_wind_speed": None,
        "annual_thunder_days": None,
        "owner_project_manager": None,
        "construction_permit_no": None,
        "epc_mode": None,
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
    "commissioning_plan": (
        "【章节约束：调试方案】\n"
        "- 必须包含：调试范围与内容、调试组织与人员、调试程序与方法、调试计划与进度\n"
        "- 须明确一次设备调试、二次系统调试、整组试验的顺序与依赖关系\n"
        "- 调试标准须引用 DL/T 5218、GB 50150 等现行规程\n"
        "- 电压等级须与 Global Facts 中 voltage_level 一致\n"
    ),
    "live_work_plan": (
        "【章节约束：带电作业方案】\n"
        "- 必须包含：作业范围、安全距离计算、工器具清单、人员资质要求\n"
        "- 须明确等电位/地电位/中间电位作业方式及选择依据\n"
        "- 安全措施须符合 DL/T 878《带电作业技术导则》\n"
        "- 必须包含停电预案和应急处置流程\n"
    ),
    "heavy_equipment_plan": (
        "【章节约束：大型设备吊装运输方案】\n"
        "- 必须包含：设备清单与重量参数、吊装方案、运输路线、地基处理\n"
        "- 主变压器吊装须明确吊车选型计算、站内行走路线\n"
        "- 须明确超限运输许可办理及交通疏导方案\n"
    ),
    "cable_laying_plan": (
        "【章节约束：电缆敷设方案】\n"
        "- 必须包含：电缆清册、敷设路径、敷设方式、弯曲半径控制\n"
        "- 须明确电缆沟/排管/桥架/直埋的选择依据\n"
        "- 高压电缆须包含交叉互联接地方案和护层保护\n"
        "- 电缆防火封堵须符合 GB 50217\n"
    ),
    "gis_installation_plan": (
        "【章节约束：GIS 安装方案】\n"
        "- 必须包含：安装环境控制（温湿度/洁净度）、SF6气体管理、对接安装工艺\n"
        "- 须明确现场交接试验项目及标准\n"
        "- 设备型号须与 Global Facts 中 substation_type 一致\n"
    ),
    "stringing_plan": (
        "【章节约束：架线施工方案】\n"
        "- 必须包含：张力放线方案、弧垂观测、压接工艺、跨越架搭设\n"
        "- 导线型号须与 Global Facts 中 conductor_type 一致\n"
        "- 跨越施工须明确被跨越物保护措施和停电协调\n"
    ),
    "tower_foundation_plan": (
        "【章节约束：铁塔基础施工方案】\n"
        "- 必须包含：基础类型选择依据、地基处理、混凝土浇筑、养护要求\n"
        "- 须明确不同地质条件下的基础设计方案\n"
        "- 杆塔数量须与 Global Facts 中 tower_count 一致\n"
    ),
    "grounding_plan": (
        "【章节约束：接地工程方案】\n"
        "- 必须包含：接地网设计参数、接地电阻要求、材料选择、施工方法\n"
        "- 须明确接地电阻测量方法和季节修正系数\n"
        "- 接地标准须符合 DL/T 621\n"
    ),
    "anti_pollution_plan": (
        "【章节约束：防污闪方案】\n"
        "- 必须包含：污区划分、爬距选择、防污措施（涂料/增爬裙/复合绝缘子）\n"
        "- 污秽等级须与 Global Facts 中 pollution_level 一致\n"
        "- 须明确清扫周期和带电水冲洗方案\n"
    ),
}

_REVIEW_CHECKLIST: dict[str, str] = {
    "construction_plan": (
        "审查要点：\n"
        "1. 工期一致性：施工进度是否与 Global Facts 工期吻合\n"
        "2. 证书一致性：项目经理资质是否与 Global Facts 一致\n"
        "3. 废标条款覆盖：是否遗漏招标文件中的废标/否决条件\n"
        "4. 参数一致性：技术参数是否与招标要求逐项对应\n"
        "5. 电压等级一致性：施工方案中电压等级是否与 Global Facts 一致\n"
    ),
    "technical_proposal": (
        "审查要点：\n"
        "1. 技术参数响应：是否逐项响应招标技术要求\n"
        "2. 标准有效性：引用的技术标准是否为现行版本\n"
        "3. 废标条款覆盖：是否遗漏技术类废标条件\n"
        "4. 一致性：技术方案与施工组织设计是否矛盾\n"
        "5. 电力设备参数：变压器容量、导线截面等参数是否与招标要求一致\n"
    ),
    "safety_plan": (
        "审查要点：\n"
        "1. 安全等级一致性：安全目标是否与招标要求一致\n"
        "2. 风险覆盖：是否覆盖各工序安全风险点\n"
        "3. 废标条款覆盖：是否遗漏安全类否决条件\n"
        "4. 应急预案完整性：是否包含必要的应急响应流程\n"
        "5. 带电作业安全：是否覆盖带电作业、高处作业等电力特有安全风险\n"
    ),
    "quality_plan": (
        "审查要点：\n"
        "1. 质量标准一致性：质量目标是否与招标要求一致\n"
        "2. 检验计划完整性：检验批划分是否合理\n"
        "3. 废标条款覆盖：是否遗漏质量类否决条件\n"
        "4. 参数一致性：质量指标是否与技术方案一致\n"
        "5. 电气试验：交接试验和预防性试验项目是否完整覆盖\n"
    ),
    "commissioning_plan": (
        "审查要点：\n"
        "1. 调试程序：是否覆盖一次设备、二次系统、整组试验全流程\n"
        "2. 标准引用：调试标准是否为现行有效版本（DL/T 5218、GB 50150）\n"
        "3. 电压等级一致性：调试方案电压等级是否与 Global Facts 一致\n"
        "4. 人员资质：调试负责人是否具备相应资质证书\n"
    ),
    "live_work_plan": (
        "审查要点：\n"
        "1. 安全距离：带电作业安全距离计算是否正确\n"
        "2. 工器具：是否列明经试验合格的带电作业工器具清单\n"
        "3. 作业方式：等电位/地电位选择是否有依据\n"
        "4. 应急预案：是否包含触电/坠落等应急处置流程\n"
    ),
    "heavy_equipment_plan": (
        "审查要点：\n"
        "1. 吊装计算：吊车选型是否经过计算校核\n"
        "2. 运输方案：超限运输路线是否经过勘查确认\n"
        "3. 地基承载力：吊装点地基处理是否充分\n"
        "4. 安全措施：大件吊装安全专项方案是否完整\n"
    ),
    "cable_laying_plan": (
        "审查要点：\n"
        "1. 电缆选型：电缆截面及型号是否与设计一致\n"
        "2. 弯曲半径：敷设弯曲半径是否满足规范要求\n"
        "3. 防火封堵：电缆防火措施是否符合 GB 50217\n"
        "4. 接地方案：高压电缆交叉互联接地是否正确\n"
    ),
    "gis_installation_plan": (
        "审查要点：\n"
        "1. 环境控制：安装环境温湿度和洁净度是否达标\n"
        "2. SF6管理：SF6气体回收和检漏措施是否完善\n"
        "3. 交接试验：现场试验项目是否覆盖完整\n"
        "4. 型号一致性：GIS 设备型号是否与招标要求一致\n"
    ),
    "stringing_plan": (
        "审查要点：\n"
        "1. 张力计算：张力放线张力是否经过计算\n"
        "2. 弧垂观测：弧垂观测方法和精度是否满足要求\n"
        "3. 跨越方案：跨越架搭设是否安全可靠\n"
        "4. 导线型号：导线型号是否与 Global Facts 一致\n"
    ),
    "tower_foundation_plan": (
        "审查要点：\n"
        "1. 基础选型：基础类型是否与地质条件匹配\n"
        "2. 混凝土质量：混凝土配合比及养护是否符合规范\n"
        "3. 杆塔数量：杆塔数量是否与 Global Facts 一致\n"
        "4. 地基处理：特殊地基处理方案是否合理\n"
    ),
    "grounding_plan": (
        "审查要点：\n"
        "1. 接地电阻：设计接地电阻值是否满足规程要求\n"
        "2. 材料选择：接地材料是否耐腐蚀并满足热稳定要求\n"
        "3. 施工方法：接地网施工焊接工艺是否规范\n"
        "4. 标准引用：接地标准是否引用 DL/T 621\n"
    ),
    "anti_pollution_plan": (
        "审查要点：\n"
        "1. 污区划分：污秽等级划分是否与 Global Facts 一致\n"
        "2. 爬距选择：爬距是否满足对应污秽等级要求\n"
        "3. 防污措施：防污措施选择是否有技术经济比较\n"
        "4. 维护方案：清扫周期和水冲洗方案是否合理\n"
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
