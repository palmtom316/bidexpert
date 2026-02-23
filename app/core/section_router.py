from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

_DEFAULT_CRITICAL_KEYWORDS = (
    "技术方案",
    "施工组织",
    "施工方案",
    "总体方案",
    "项目实施方案",
    "技术路线",
    "工艺流程",
    "关键工序",
    "施工部署",
    "进度计划",
    "工期",
    "资源配置",
    "人员组织",
    "组织机构",
    "劳动力",
    "设备",
    "机械",
    "材料计划",
    "质量",
    "质量保证",
    "质量控制",
    "质量管理",
    "安全",
    "文明施工",
    "HSE",
    "风险",
    "应急预案",
    "环保",
    "职业健康",
    "商务响应",
    "偏离表",
    "响应表",
    "资格",
    "资信",
    "承诺函",
    "业绩",
    "类似项目",
    "条款响应",
    "报价",
    "清单",
    "计价",
)


@dataclass(frozen=True)
class SectionRoutingConfig:
    critical_keywords: tuple[str, ...]
    critical_weight_threshold: float


@dataclass(frozen=True)
class SectionGenerationPlan:
    is_critical: bool
    base_model: tuple[str, str]
    post_enhance_model: tuple[str, str] | None
    review_model: tuple[str, str]


def _config_path() -> Path:
    override = (
        os.getenv("SECTION_ROUTING_PATH")
        or os.getenv("BIDEXPERT_SECTION_ROUTING_PATH")
        or ""
    ).strip()
    if override:
        path = Path(override).expanduser()
        if path.is_absolute():
            return path
        return Path.cwd() / path
    return Path(__file__).resolve().parent.parent / "config" / "section_routing.cn.json"


@lru_cache(maxsize=1)
def load_section_routing_config() -> SectionRoutingConfig:
    path = _config_path()
    if not path.exists():
        return SectionRoutingConfig(
            critical_keywords=_DEFAULT_CRITICAL_KEYWORDS,
            critical_weight_threshold=0.7,
        )

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("section routing config must be an object")

    raw_keywords = payload.get("critical_keywords")
    keywords: list[str] = []
    if isinstance(raw_keywords, list):
        for item in raw_keywords:
            token = str(item).strip()
            if token:
                keywords.append(token)

    raw_threshold = payload.get("critical_weight_threshold", 0.7)
    try:
        threshold = float(raw_threshold)
    except (TypeError, ValueError):
        threshold = 0.7

    return SectionRoutingConfig(
        critical_keywords=tuple(keywords) if keywords else _DEFAULT_CRITICAL_KEYWORDS,
        critical_weight_threshold=max(0.0, threshold),
    )


def _value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _safe_title(section: Any) -> str:
    for key in ("title", "section_title", "chapter_path", "heading"):
        value = _value(section, key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _safe_weight(section: Any) -> float | None:
    value = _value(section, "weight")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def is_critical_section(section: Any, *, config: SectionRoutingConfig | None = None) -> bool:
    active_config = config or load_section_routing_config()
    weight = _safe_weight(section)
    if weight is not None and weight >= active_config.critical_weight_threshold:
        return True

    title = _safe_title(section)
    if not title:
        return False

    normalized_title = title.lower()
    for keyword in active_config.critical_keywords:
        token = str(keyword).strip()
        if not token:
            continue
        if token.lower() in normalized_title:
            return True
    return False


def select_generation_plan(section: Any, env_mode: str) -> SectionGenerationPlan:
    normalized_mode = (env_mode or "prod").strip().lower()
    critical = is_critical_section(section)

    if normalized_mode == "debug":
        base_model = ("qwen", "qwen-plus")
    else:
        base_model = ("qwen", "qwen-max")

    review_model = ("deepseek", "deepseek-reasoner")
    enhance_model = review_model if critical else None

    return SectionGenerationPlan(
        is_critical=critical,
        base_model=base_model,
        post_enhance_model=enhance_model,
        review_model=review_model,
    )


__all__ = [
    "SectionGenerationPlan",
    "SectionRoutingConfig",
    "is_critical_section",
    "load_section_routing_config",
    "select_generation_plan",
]
