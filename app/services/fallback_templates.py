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
    }.get(section_type, section_type)

    return template.format(
        project_name=project_name or "【请补充：项目名称】",
        requirement_text=requirement_text or "【请补充：招标要求】",
        evidence_section=evidence_section,
        section_type_label=section_type_label,
    )
