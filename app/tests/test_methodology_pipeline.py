from __future__ import annotations

import pytest

from app.services.methodology.publish import ensure_publish_allowed
from app.services.methodology.risk_scan import assess_source_risk
from app.services.methodology.sanitize import remove_pii
from app.services.methodology.similarity import evaluate_similarity


def test_sanitize_removes_phone_and_id() -> None:
    text = "联系人：张三，电话 13800138000，身份证 11010519491231002X"
    result = remove_pii(text)

    assert result.pii_removed is True
    assert "13800138000" not in result.sanitized_text
    assert "11010519491231002X" not in result.sanitized_text


def test_risk_scan_blocks_unknown_source_without_approval() -> None:
    result = assess_source_risk(source_type="unknown", findings=[])

    assert result.risk_level == "high"
    assert result.blocked is True
    assert "L0" in result.blocking_gate


def test_similarity_gate_marks_need_edit_when_high_overlap() -> None:
    source = "施工组织设计应包括进度计划、质量保障和安全文明措施。"
    rewritten = "施工组织设计应包括进度计划、质量保障和安全文明措施。"

    result = evaluate_similarity(source_text=source, rewritten_text=rewritten, threshold=0.35)

    assert result.score > 0.35
    assert result.decision == "need_edit"


def test_review_required_before_publish() -> None:
    with pytest.raises(ValueError, match="review status must be approved"):
        ensure_publish_allowed(review_status="need_edit", risk_level="low")

    # Approved + non-high risk can publish
    ensure_publish_allowed(review_status="approved", risk_level="medium")
