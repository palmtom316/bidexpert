from __future__ import annotations

import re
from collections import Counter

_DEFAULT_STRUCTURE = [
    "目标与原则",
    "组织保障",
    "技术保障",
    "资源保障",
    "风险预案",
]


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。；;\n]+", text or "")
    return [part.strip() for part in parts if part and part.strip()]


def _auto_tags(text: str, provided_tags: list[str]) -> list[str]:
    tags = [tag.strip() for tag in provided_tags if tag and tag.strip()]
    keyword_map = {
        "进度": ["进度", "工期", "里程碑"],
        "质量": ["质量", "验收", "缺陷"],
        "安全": ["安全", "风险", "应急"],
        "资源": ["资源", "材料", "设备", "人员"],
    }
    normalized = text or ""
    for tag, words in keyword_map.items():
        if tag in tags:
            continue
        if any(word in normalized for word in words):
            tags.append(tag)
    if not tags:
        tokens = [token for token, _ in Counter(re.findall(r"[\u4e00-\u9fff]{2,4}", normalized)).most_common(3)]
        tags.extend(tokens)
    return tags[:8]


def extract_methodology_assets(*, sanitized_text: str, domain: str | None, tags: list[str] | None) -> dict:
    text = (sanitized_text or "").strip()
    lines = _split_sentences(text)
    selected = lines[:5] if lines else ["结合项目实际制定可执行措施。"]

    title_seed = selected[0][:18] if selected else "通用方法"
    title = f"{title_seed}（通用框架）"

    template_lines = ["### 方法论模板（通用）"]
    for idx, item in enumerate(selected, start=1):
        template_lines.append(f"{idx}. {item}")
    template_md = "\n".join(template_lines)

    resolved_tags = _auto_tags(text, tags or [])

    return {
        "title": title,
        "domain": (domain or "通用").strip() or "通用",
        "tags": resolved_tags,
        "applicability": {
            "voltage_level_kv": [],
            "project_type": ["通用"],
            "region": ["通用"],
        },
        "structure": _DEFAULT_STRUCTURE,
        "template_md": template_md,
    }
