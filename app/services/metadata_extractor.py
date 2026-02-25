"""v1.4 — Metadata Auto-Tagging Engine.

Extract voltage_level_kv / project_type / core_equipment / region from
document text using regex-first with optional LLM fallback.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Voltage extraction ──────────────────────────────────────────
_VOLTAGE_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*[kK][vV]",
    re.UNICODE,
)
_KNOWN_VOLTAGES = {10, 20, 35, 66, 110, 220, 330, 500, 750, 1000}


# ── Project type extraction ─────────────────────────────────────
_PROJECT_TYPE_KEYWORDS = {
    "新建": "新建",
    "改造": "改造",
    "扩建": "扩建",
    "业扩配电": "业扩配电",
    "业扩": "业扩配电",
    "技改": "改造",
    "迁改": "改造",
    "增容": "扩建",
}

# ── Core equipment extraction ───────────────────────────────────
_EQUIPMENT_KEYWORDS = [
    "变压器", "开关柜", "电缆", "断路器", "隔离开关",
    "互感器", "电容器", "避雷器", "母线", "GIS",
    "充电桩", "箱变", "环网柜", "配电柜", "接地装置",
    "电抗器", "刀闸", "熔断器", "继电保护", "无功补偿",
]

# ── Region (province) extraction ────────────────────────────────
_PROVINCES = [
    "北京", "天津", "上海", "重庆",
    "河北", "山西", "辽宁", "吉林", "黑龙江",
    "江苏", "浙江", "安徽", "福建", "江西", "山东",
    "河南", "湖北", "湖南", "广东", "海南",
    "四川", "贵州", "云南", "陕西", "甘肃",
    "青海", "台湾",
    "内蒙古", "广西", "西藏", "宁夏", "新疆",
]
# Also match "XX省" / "XX市" / "XX自治区" patterns
_REGION_RE = re.compile(
    r"(" + "|".join(re.escape(p) for p in _PROVINCES) + r")"
    r"(?:省|市|自治区|自治州)?",
    re.UNICODE,
)


@dataclass
class DocumentMetadata:
    voltage_level_kv: int | None = None
    project_type: str | None = None
    core_equipment: list[str] = field(default_factory=list)
    region: str | None = None

    def to_dict(self) -> dict:
        return {
            "voltage_level_kv": self.voltage_level_kv,
            "project_type": self.project_type,
            "core_equipment": self.core_equipment,
            "region": self.region,
        }

    def has_gaps(self) -> bool:
        return (
            self.voltage_level_kv is None
            or self.project_type is None
            or not self.core_equipment
            or self.region is None
        )

    def merge(self, other: DocumentMetadata) -> DocumentMetadata:
        """Fill gaps from another metadata result (LLM fallback)."""
        return DocumentMetadata(
            voltage_level_kv=self.voltage_level_kv or other.voltage_level_kv,
            project_type=self.project_type or other.project_type,
            core_equipment=self.core_equipment or other.core_equipment,
            region=self.region or other.region,
        )


def extract_metadata_regex(text: str) -> DocumentMetadata:
    """Primary: regex-based extraction of metadata fields."""
    snippet = (text or "")[:8000]

    # Voltage
    voltage_level_kv: int | None = None
    voltage_matches = _VOLTAGE_RE.findall(snippet)
    if voltage_matches:
        for v_str in voltage_matches:
            try:
                v = int(float(v_str))
                if v in _KNOWN_VOLTAGES:
                    voltage_level_kv = v
                    break
            except (ValueError, OverflowError):
                continue
        if voltage_level_kv is None and voltage_matches:
            try:
                voltage_level_kv = int(float(voltage_matches[0]))
            except (ValueError, OverflowError):
                pass

    # Project type
    project_type: str | None = None
    for keyword, pt_value in _PROJECT_TYPE_KEYWORDS.items():
        if keyword in snippet:
            project_type = pt_value
            break

    # Core equipment
    core_equipment: list[str] = []
    seen: set[str] = set()
    for eq in _EQUIPMENT_KEYWORDS:
        if eq in snippet and eq not in seen:
            core_equipment.append(eq)
            seen.add(eq)

    # Region
    region: str | None = None
    region_match = _REGION_RE.search(snippet)
    if region_match:
        region = region_match.group(1)

    return DocumentMetadata(
        voltage_level_kv=voltage_level_kv,
        project_type=project_type,
        core_equipment=core_equipment,
        region=region,
    )


def extract_metadata_llm(text: str, model_id: str | None = None) -> DocumentMetadata:
    """Fallback: lightweight LLM extraction for cases regex misses."""
    from app.services.byok import resolve_profile_for_task

    profile = resolve_profile_for_task(project_id=None, task_type="EXTRACT")
    model = model_id or settings.metadata_llm_model
    base_url = profile.base_url
    api_key = profile.api_key

    if not api_key or not base_url:
        logger.warning("metadata LLM fallback skipped: no EXTRACT profile credentials")
        return DocumentMetadata()

    snippet = (text or "")[:4000]
    prompt = (
        "从以下电力工程文本中提取以下字段，返回JSON对象：\n"
        "- voltage_level_kv: 电压等级(kV整数)，如10/35/110/220\n"
        "- project_type: 工程类型，可选值：新建/改造/扩建/业扩配电\n"
        "- core_equipment: 核心设备列表，如[\"变压器\",\"开关柜\"]\n"
        "- region: 所在省份，如\"江苏\"\n\n"
        "如果某字段无法确定，设为null。只输出JSON，不要其他内容。\n\n"
        f"文本：{snippet}"
    )

    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "You extract structured metadata from Chinese power engineering documents. Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=float(settings.llm_http_timeout_seconds),
        )
        resp.raise_for_status()
        payload = resp.json()
        content = payload.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(content) if content else {}
    except Exception:
        logger.warning("metadata LLM fallback failed", exc_info=True)
        return DocumentMetadata()

    voltage = parsed.get("voltage_level_kv")
    equipment = parsed.get("core_equipment")
    return DocumentMetadata(
        voltage_level_kv=int(voltage) if voltage is not None else None,
        project_type=parsed.get("project_type"),
        core_equipment=equipment if isinstance(equipment, list) else [],
        region=parsed.get("region"),
    )


def extract_metadata(text: str, *, use_llm_fallback: bool = True) -> DocumentMetadata:
    """Combined: regex first, LLM fills gaps if enabled."""
    result = extract_metadata_regex(text)

    if result.has_gaps() and use_llm_fallback and settings.metadata_llm_fallback_enabled:
        try:
            llm_result = extract_metadata_llm(text)
            result = result.merge(llm_result)
        except Exception:
            logger.warning("metadata LLM fallback error; using regex-only result", exc_info=True)

    return result
