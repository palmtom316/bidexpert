"""Task 15: 生成管线冲突与废标检测 (R24).

Tests for global fact conflict detection and disqualify keyword interaction.
"""
from __future__ import annotations

from app.services.global_facts import detect_global_fact_conflicts


def test_conflict_on_different_duration() -> None:
    base = {"total_duration_days": "180天"}
    candidate = {"total_duration_days": "240天"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) >= 1
    assert any("total_duration_days" in c for c in conflicts)


def test_no_conflict_on_same_values() -> None:
    base = {"project_name": "测试项目", "total_duration_days": "180天"}
    candidate = {"project_name": "测试项目", "total_duration_days": "180天"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) == 0


def test_conflict_on_different_quality_standard() -> None:
    base = {"quality_standard": "合格"}
    candidate = {"quality_standard": "优良"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) >= 1


def test_conflict_on_different_location() -> None:
    base = {"project_location": "北京市朝阳区"}
    candidate = {"project_location": "上海市浦东新区"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) >= 1


def test_no_conflict_when_candidate_empty() -> None:
    base = {"project_duration": "180天", "quality_standard": "合格"}
    candidate = {}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) == 0


def test_multiple_conflicts_detected() -> None:
    base = {"total_duration_days": "180天", "quality_standard": "合格", "safety_level": "一级"}
    candidate = {"total_duration_days": "240天", "quality_standard": "优良", "safety_level": "二级"}
    conflicts = detect_global_fact_conflicts(base, candidate)
    assert len(conflicts) >= 3
