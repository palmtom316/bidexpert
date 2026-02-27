"""Power engineering PII whitelist tests."""
from __future__ import annotations

from app.services.pii_policy import (
    _BID_PERSONNEL_CONTEXT,
    _ENTERPRISE_CREDENTIAL,
    _CREDENTIAL_NUMBER,
    _mask_pii,
)


def test_bid_personnel_context_matches_project_manager():
    assert _BID_PERSONNEL_CONTEXT.search("项目经理：张三")


def test_bid_personnel_context_matches_safety_officer():
    assert _BID_PERSONNEL_CONTEXT.search("专职安全员")


def test_enterprise_credential_matches():
    assert _ENTERPRISE_CREDENTIAL.search("统一社会信用代码")
    assert _ENTERPRISE_CREDENTIAL.search("承装修试许可证编号")


def test_credential_number_extracts():
    text = "统一社会信用代码：91110000MA01B1234X"
    match = _CREDENTIAL_NUMBER.search(text)
    assert match is not None
    assert "91110000MA01B1234X" in match.group(1)


def test_phone_preserved_in_personnel_context():
    text = "项目经理：张三，联系电话13812345678"
    masked = _mask_pii(text)
    # Phone should be preserved because it's near 项目经理
    assert "13812345678" in masked


def test_phone_masked_outside_personnel_context():
    text = "个人手机号码是13812345678请勿泄露"
    masked = _mask_pii(text)
    assert "13812345678" not in masked
