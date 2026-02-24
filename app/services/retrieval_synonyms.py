"""Synonym expansion for retrieval queries (R21)."""
from __future__ import annotations

SYNONYM_DICT: dict[str, list[str]] = {
    "施工组织设计": ["施工方案", "施组"],
    "施工方案": ["施工组织设计", "施组"],
    "项目经理": ["项目负责人", "工程负责人"],
    "项目负责人": ["项目经理", "工程负责人"],
    "安全生产": ["安全管理", "安全施工"],
    "安全管理": ["安全生产", "安全施工"],
    "质量管理": ["质量保证", "质量控制", "质保体系"],
    "质量保证": ["质量管理", "质量控制"],
    "环境保护": ["环保措施", "环保方案"],
    "环保措施": ["环境保护", "环保方案"],
    "工期": ["工程期限", "施工工期", "合同工期"],
    "投标保证金": ["投标担保", "保证金"],
    "履约保证金": ["履约担保", "履约保函"],
    "分包": ["专业分包", "劳务分包"],
    "资质": ["资质证书", "资质等级"],
    "业绩": ["工程业绩", "类似业绩", "项目业绩"],
    "技术标": ["技术方案", "技术文件"],
    "商务标": ["商务方案", "商务文件"],
    "评标": ["评审", "评标委员会"],
}


def expand_synonyms(term: str) -> list[str]:
    """Return the original term plus any known synonyms."""
    result = [term]
    aliases = SYNONYM_DICT.get(term, [])
    for alias in aliases:
        if alias not in result:
            result.append(alias)
    return result
