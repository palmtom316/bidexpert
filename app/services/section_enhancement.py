from __future__ import annotations

import re
from collections import Counter

CLAUDE_SECTION_ENHANCEMENT_PROMPT = """你是电力与建筑工程投标文件/施工规范的结构增强分析专家。

任务：对以下“单个章节（section）”做语义增强标注，并输出严格 JSON（只允许输出 JSON；不得输出解释性文字）。

你必须：
- 只依据输入文本判断，不得编造。
- 信息不足时在 summary 说明“不足”，并降低 confidence。
- keywords 选 5-15 个，尽量是可检索的工程术语。

字段枚举（必须从以下选择）：

section_type ∈
[技术方案, 商务部分, 资质文件, 业绩材料, 施工组织, 安全文明施工, 质量保证, 进度计划, 报价说明, 合同条款响应, 其他]

discipline ∈
[电气, 土建, 暖通, 给排水, 通信, 结构, 综合, 其他]

project_phase ∈
[投标文件, 施工规范, 施工组织设计, 竣工资料, 通用规范]

reusability ∈ [high, medium, low]
compliance_risk_level ∈ [high, medium, low, none]

判定规则（重要）：

contains_score_items = true 若章节涉及：
- 评分标准响应 / 技术评分点展开 / 工期与资源得分点
- 类似业绩与人员简历评分点
- 技术参数优势与对比（倾向得分点）

contains_compliance_items = true 若章节涉及：
- 必须满足 / 否则否决 / 废标 / 不响应即否决 / 强制性条款
- 合同实质性响应 / 偏差表 / 资格条件硬性要求

reusability = high 若：
- 内容为通用方法、制度、流程、模板段落
- 与具体项目专属数值/地名/单位绑定较少

输出 JSON 模板（不得新增字段）：

{
  "section_id": "",
  "section_title": "",
  "section_type": "",
  "discipline": "",
  "project_phase": "",
  "reusability": "",
  "contains_score_items": false,
  "contains_compliance_items": false,
  "score_related_topics": [],
  "compliance_risk_level": "",
  "keywords": [],
  "summary": "",
  "confidence": 0.00
}

输入如下：

【section_id】
{{SECTION_ID}}

【章节标题】
{{TITLE}}

【页码范围】
{{PAGE_START}}-{{PAGE_END}}

【章节正文】
{{CONTENT}}

【表格摘要】
{{TABLE_SUMMARY}}"""

CLAUDE_RISK_REVIEW_PROMPT = """你是投标文件“评分点/合规废标点”复核专家。

任务：仅判断该章节是否属于“评分关键点”或“合规/废标关键点”，并给出简短依据。
只输出严格 JSON（不得输出解释性文字）。

输出 JSON（不得新增字段）：
{
  "section_id": "",
  "is_score_critical": false,
  "is_compliance_critical": false,
  "compliance_risk_level": "none",
  "evidence_quotes": [
    {"quote": "", "page": 0}
  ],
  "reason": "",
  "confidence": 0.00
}

规则：
- evidence_quotes 最多 3 条，每条 quote ≤ 80 字，必须来自原文。
- 如果无法找到原文直接依据，confidence 降低，并说明“未找到明确句子”。
- 若判断为 high，必须至少给出 1 条 evidence_quotes。

输入：
【section_id】{{SECTION_ID}}
【页码范围】{{PAGE_START}}-{{PAGE_END}}
【正文】{{CONTENT}}"""

CLAUDE_TABLE_SUMMARY_PROMPT = """你是工程投标文档表格摘要器。

任务：将输入的表格（二维数据或转写文本）生成一个短摘要，用于后续章节理解。
只输出 JSON。不得输出解释性文字。

输出：
{
  "table_title_guess": "",
  "table_type": "其他",
  "key_columns": [],
  "row_count_est": 0,
  "notes": ""
}

输入表格：
{{TABLE_RAW}}"""

CLAUDE_JSON_REPAIR_PROMPT = """你是 JSON 修复器。

任务：把“模型输出”修复成合法 JSON，且字段必须完全符合给定 schema。
只输出修复后的 JSON；不得输出其他文字。

约束：
- 不能新增字段、不能删除字段
- 布尔值必须是 true/false
- confidence 必须是 0-1 的数字

【schema】
{{SCHEMA_JSON}}

【model_output】
{{MODEL_OUTPUT}}"""

_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}")
_STOPWORDS = {
    "以及",
    "根据",
    "相关",
    "要求",
    "项目",
    "进行",
    "投标",
    "文件",
    "条款",
    "内容",
}


def _keywords(text: str, limit: int = 8) -> list[str]:
    tokens = [tok for tok in _TOKEN_PATTERN.findall(text) if tok not in _STOPWORDS]
    if not tokens:
        return []
    ranked = Counter(tokens).most_common(limit)
    return [item[0] for item in ranked]


def _discipline(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ("电力", "电气", "变电", "输电", "配电")):
        return "ELECTRICAL"
    if any(k in lowered for k in ("土建", "结构", "建筑", "房建", "基坑")):
        return "CIVIL"
    return "GENERAL"


def _section_type(title: str, text: str) -> str:
    scope = f"{title}\n{text}"
    if re.search(r"评分|得分|分值|打分", scope):
        return "SCORING"
    if re.search(r"资质|资格|业绩", scope):
        return "QUALIFICATION"
    if re.search(r"合同|合规|必须|应当|不得|须", scope):
        return "COMPLIANCE"
    if re.search(r"技术|方案|工艺|实施", scope):
        return "TECHNICAL"
    return "GENERAL"


def _project_phase(scope: str) -> str:
    if re.search(r"施工|实施|交付|验收", scope):
        return "CONSTRUCTION"
    if re.search(r"设计|深化|图纸", scope):
        return "DESIGN"
    return "BIDDING"


def _reusability(section_type: str, contains_score_items: bool) -> str:
    if section_type in {"QUALIFICATION", "COMPLIANCE"} and not contains_score_items:
        return "HIGH"
    if section_type in {"TECHNICAL", "SCORING"}:
        return "MEDIUM"
    return "LOW"


def _risk_level(contains_compliance_items: bool, contains_score_items: bool) -> str:
    if contains_compliance_items and contains_score_items:
        return "HIGH"
    if contains_compliance_items:
        return "MEDIUM"
    return "LOW"


def enhance_section_metadata(section_id: str, section_title: str, section_text: str) -> dict:
    contains_score_items = bool(re.search(r"评分|得分|分值|打分", section_text))
    contains_compliance_items = bool(re.search(r"必须|应当|不得|须|严禁", section_text))
    section_type = _section_type(section_title, section_text)
    discipline = _discipline(f"{section_title}\n{section_text}")
    project_phase = _project_phase(f"{section_title}\n{section_text}")
    keywords = _keywords(f"{section_title}\n{section_text}")
    summary = section_text.strip().replace("\n", " ")
    if len(summary) > 160:
        summary = f"{summary[:157]}..."

    return {
        "section_id": section_id,
        "section_title": section_title,
        "section_type": section_type,
        "discipline": discipline,
        "project_phase": project_phase,
        "reusability": _reusability(section_type, contains_score_items),
        "contains_score_items": contains_score_items,
        "contains_compliance_items": contains_compliance_items,
        "score_related_topics": ["评分标准"] if contains_score_items else [],
        "compliance_risk_level": _risk_level(contains_compliance_items, contains_score_items),
        "keywords": keywords,
        "summary": summary,
        "confidence": 0.85 if keywords else 0.7,
    }
