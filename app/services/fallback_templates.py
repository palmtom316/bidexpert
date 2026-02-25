"""Offline fallback templates for when all LLM providers are unavailable.

Provides structured, human-editable section skeletons with placeholder
markers so users can fill in project-specific details manually.
"""
from __future__ import annotations

_SECTION_TEMPLATES: dict[str, str] = {
    "construction_plan": (
        "# 施工组织设计\n\n"
        "## 一、编制依据\n\n"
        "本施工组织设计依据以下文件编制：\n"
        "- 【{project_name}】招标文件及其补充文件\n"
        "- 国家及地方现行施工规范、标准\n"
        "- GB 50233《110kV~750kV架空输电线路施工及验收规范》\n"
        "- GB 50168~GB 50171 电气装置安装工程系列标准\n"
        "- DL/T 5161《电气装置安装工程质量检验及评定规程》\n"
        "- 【请补充：相关图纸及技术资料】\n\n"
        "## 二、工程概况\n\n"
        "工程名称：【{project_name}】\n"
        "工程地点：【请补充：工程地点】\n"
        "建设单位：【请补充：建设单位名称】\n"
        "工程规模：【请补充：工程规模描述】\n"
        "工期要求：【请补充：合同工期】\n"
        "质量目标：【请补充：质量等级要求】\n\n"
        "## 三、总体施工部署\n\n"
        "### 3.1 施工组织机构\n"
        "【请补充：项目组织架构及主要管理人员】\n\n"
        "### 3.2 施工总体安排\n"
        "根据招标文件要求：{requirement_text}\n\n"
        "{evidence_section}"
        "【请补充：施工顺序及阶段划分】\n\n"
        "## 四、施工进度计划\n\n"
        "【请补充：关键节点工期及进度计划表】\n\n"
        "## 五、主要施工方法\n\n"
        "【请补充：各分部分项工程施工方法】\n\n"
        "## 六、质量保证措施\n\n"
        "【请补充：质量管理体系及控制措施】\n\n"
        "## 七、安全文明施工措施\n\n"
        "【请补充：安全管理体系及文明施工措施】\n"
    ),
    "technical_proposal": (
        "# 技术方案\n\n"
        "## 一、技术方案概述\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "## 二、技术路线\n\n"
        "【请补充：技术路线及方案选型】\n\n"
        "## 三、关键技术措施\n\n"
        "【请补充：关键技术难点及解决方案】\n\n"
        "## 四、技术保障\n\n"
        "【请补充：技术人员配置及技术管理措施】\n"
    ),
    "safety_plan": (
        "# 安全生产方案\n\n"
        "## 一、安全管理目标\n\n"
        "针对【{project_name}】项目：{requirement_text}\n\n"
        "{evidence_section}"
        "## 二、安全管理组织机构\n\n"
        "【请补充：安全管理架构及职责分工】\n\n"
        "## 三、安全技术措施\n\n"
        "【请补充：各工序安全技术措施】\n\n"
        "## 四、应急预案\n\n"
        "【请补充：安全事故应急预案】\n"
    ),
    "quality_plan": (
        "# 质量保证方案\n\n"
        "## 一、质量目标\n\n"
        "针对【{project_name}】项目：{requirement_text}\n\n"
        "{evidence_section}"
        "## 二、质量管理体系\n\n"
        "【请补充：质量管理组织及制度】\n\n"
        "## 三、质量控制措施\n\n"
        "【请补充：各分部分项质量控制要点】\n\n"
        "## 四、质量检验计划\n\n"
        "【请补充：检验批划分及验收标准】\n"
    ),
    "commissioning_plan": (
        "# 调试方案\n\n"
        "## 一、编制依据\n\n"
        "本调试方案依据以下文件编制：\n"
        "- 【{project_name}】招标文件及其补充文件\n"
        "- DL/T 5218《220kV~750kV变电站设计技术规程》\n"
        "- GB 50150《电气装置安装工程电气设备交接试验标准》\n"
        "- 【请补充：设备厂家调试手册】\n\n"
        "## 二、调试范围与内容\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "### 2.1 一次设备调试\n"
        "【请补充：变压器、断路器、隔离开关等一次设备调试项目】\n\n"
        "### 2.2 二次系统调试\n"
        "【请补充：继电保护、自动化、通信系统调试项目】\n\n"
        "### 2.3 整组试验\n"
        "【请补充：整组传动试验、保护联动试验项目】\n\n"
        "## 三、调试组织与人员\n\n"
        "【请补充：调试人员资质要求及组织架构】\n\n"
        "## 四、调试进度计划\n\n"
        "【请补充：各阶段调试计划及关键节点】\n\n"
        "## 五、安全措施\n\n"
        "【请补充：调试期间安全措施及应急预案】\n"
    ),
    "stringing_plan": (
        "# 架线施工方案\n\n"
        "## 一、编制依据\n\n"
        "- 【{project_name}】招标文件\n"
        "- GB 50233《110kV~750kV架空输电线路施工及验收规范》\n\n"
        "## 二、工程概况\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "## 三、张力放线方案\n\n"
        "【请补充：放线设备选型、张力计算、放线速度控制】\n\n"
        "## 四、弧垂观测\n\n"
        "【请补充：观测方法、温度修正、精度要求】\n\n"
        "## 五、跨越施工\n\n"
        "【请补充：跨越架搭设、被跨越物保护、停电协调】\n\n"
        "## 六、压接工艺\n\n"
        "【请补充：液压压接参数、耐张线夹安装】\n"
    ),
    "equipment_installation_plan": (
        "# 设备安装方案\n\n"
        "## 一、编制依据\n\n"
        "- 【{project_name}】招标文件\n"
        "- GB 50168~GB 50171 电气装置安装工程系列标准\n\n"
        "## 二、设备清单\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "【请补充：主要设备清单含型号、数量、重量】\n\n"
        "## 三、运输方案\n\n"
        "【请补充：大型设备运输路线、超限运输许可】\n\n"
        "## 四、吊装方案\n\n"
        "【请补充：吊车选型计算、地基处理、吊装步骤】\n\n"
        "## 五、安装工艺\n\n"
        "【请补充：各设备安装工艺要求及质量标准】\n"
    ),
    "grounding_plan": (
        "# 接地工程方案\n\n"
        "## 一、编制依据\n\n"
        "- 【{project_name}】招标文件\n"
        "- DL/T 621《交流电气装置的接地设计规范》\n"
        "- GB 50169《电气装置安装工程接地装置施工及验收规范》\n\n"
        "## 二、设计参数\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "【请补充：接地电阻要求、接地网面积、材料选择】\n\n"
        "## 三、施工方法\n\n"
        "【请补充：开挖、焊接、回填工艺要求】\n\n"
        "## 四、接地电阻测量\n\n"
        "【请补充：测量方法、季节修正系数、合格标准】\n"
    ),
    "cable_laying_plan": (
        "# 电缆敷设方案\n\n"
        "## 一、编制依据\n\n"
        "- 【{project_name}】招标文件\n"
        "- GB 50217《电力工程电缆设计标准》\n"
        "- GB 50168《电气装置安装工程电缆线路施工及验收标准》\n\n"
        "## 二、电缆清册\n\n"
        "针对【{project_name}】项目要求：{requirement_text}\n\n"
        "{evidence_section}"
        "【请补充：电缆型号、截面、长度、起止点】\n\n"
        "## 三、敷设方式\n\n"
        "【请补充：电缆沟/排管/桥架/直埋选择依据】\n\n"
        "## 四、弯曲半径控制\n\n"
        "【请补充：各类型电缆最小弯曲半径】\n\n"
        "## 五、防火封堵\n\n"
        "【请补充：防火封堵材料及施工要求】\n"
    ),
}

_GENERIC_TEMPLATE = (
    "# 【{section_type_label}】\n\n"
    "## 一、概述\n\n"
    "针对【{project_name}】项目要求：{requirement_text}\n\n"
    "{evidence_section}"
    "## 二、实施方案\n\n"
    "【请补充：具体实施方案及措施】\n\n"
    "## 三、保障措施\n\n"
    "【请补充：组织、技术、资源保障措施】\n"
)


def render_fallback_template(
    *,
    section_type: str,
    requirement_text: str,
    project_name: str | None = None,
    evidence_texts: list[str] | None = None,
) -> str:
    template = _SECTION_TEMPLATES.get(section_type, _GENERIC_TEMPLATE)

    evidence_section = ""
    if evidence_texts:
        lines = ["我方相关能力与业绩：\n"]
        for i, text in enumerate(evidence_texts[:5], 1):
            snippet = text.strip()[:200]
            lines.append(f"- {snippet}")
        lines.append("\n")
        evidence_section = "\n".join(lines)

    section_type_label = {
        "construction_plan": "施工组织设计",
        "technical_proposal": "技术方案",
        "safety_plan": "安全生产方案",
        "quality_plan": "质量保证方案",
        "schedule_plan": "施工进度计划",
        "environmental_plan": "环境保护方案",
        "resource_plan": "资源配置方案",
        "commercial_proposal": "商务方案",
        "commissioning_plan": "调试方案",
        "stringing_plan": "架线施工方案",
        "equipment_installation_plan": "设备安装方案",
        "grounding_plan": "接地工程方案",
        "cable_laying_plan": "电缆敷设方案",
    }.get(section_type, section_type)

    return template.format(
        project_name=project_name or "【请补充：项目名称】",
        requirement_text=requirement_text or "【请补充：招标要求】",
        evidence_section=evidence_section,
        section_type_label=section_type_label,
    )
