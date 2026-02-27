"""Tests for G2 active check validators: qualifications, key staff, authorization."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from unittest.mock import patch

import pytest

from app.schemas.contracts import RedlineCheckRequest, RedlineFinding
from app.services.redline_engine import (
    check_authorization,
    check_key_staff_and_ss,
    check_qualifications,
    run_redline_check,
)


# ── check_qualifications ─────────────────────────────────────


def test_check_qualifications_returns_p0_when_pool_empty():
    with patch("app.tender.assets.repository.get_company_qualifications", return_value=[]):
        findings = check_qualifications(
            project_id="proj-1",
            tender_package_id="pkg-1",
        )
    assert len(findings) == 1
    assert findings[0].severity == "P0"
    assert findings[0].rule_id == "QUAL-MISSING"


def test_check_qualifications_returns_p0_when_expired():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    quals = [
        {"id": "q-1", "title": "电力工程施工总承包", "doc_type": "QUALIFICATION", "valid_to": yesterday},
    ]
    with patch("app.tender.assets.repository.get_company_qualifications", return_value=quals):
        findings = check_qualifications(
            project_id="proj-1",
            tender_package_id="pkg-1",
        )
    expired = [f for f in findings if "QUAL-EXPIRED" in f.rule_id]
    assert len(expired) == 1
    assert expired[0].severity == "P0"


def test_check_qualifications_passes_when_valid():
    future = (date.today() + timedelta(days=365)).isoformat()
    quals = [
        {"id": "q-1", "title": "电力工程施工总承包", "doc_type": "QUALIFICATION", "valid_to": future},
    ]
    with patch("app.tender.assets.repository.get_company_qualifications", return_value=quals):
        findings = check_qualifications(
            project_id="proj-1",
            tender_package_id="pkg-1",
        )
    assert len(findings) == 0


# ── check_key_staff_and_ss ───────────────────────────────────


def test_check_key_staff_returns_p0_when_pool_empty():
    project_id = str(uuid.uuid4())
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_personnel_candidates_from_asset_pool",
            return_value=[],
        ):
            findings = check_key_staff_and_ss(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    assert len(findings) == 1
    assert findings[0].severity == "P0"
    assert findings[0].rule_id == "STAFF-POOL-EMPTY"


def test_check_key_staff_detects_concurrent_project_conflict():
    project_id = str(uuid.uuid4())
    candidates = [
        {
            "asset_pool_id": "ap-1",
            "asset_name": "张三",
            "active_project_count": 2,
            "social_security_months": 24,
            "evidence_refs": ["E-1"],
        },
    ]
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_personnel_candidates_from_asset_pool",
            return_value=candidates,
        ):
            findings = check_key_staff_and_ss(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    conflict = [f for f in findings if "STAFF-CONFLICT" in f.rule_id]
    assert len(conflict) == 1
    assert conflict[0].severity == "P1"


def test_check_key_staff_detects_low_social_security():
    project_id = str(uuid.uuid4())
    candidates = [
        {
            "asset_pool_id": "ap-2",
            "asset_name": "李四",
            "active_project_count": 0,
            "social_security_months": 3,
            "evidence_refs": [],
        },
    ]
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_personnel_candidates_from_asset_pool",
            return_value=candidates,
        ):
            findings = check_key_staff_and_ss(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    ss_low = [f for f in findings if "STAFF-SS-LOW" in f.rule_id]
    assert len(ss_low) == 1
    assert ss_low[0].severity == "P1"


def test_check_key_staff_invalid_project_id():
    findings = check_key_staff_and_ss(
        project_id="not-a-uuid",
        tender_package_id="pkg-1",
    )
    assert len(findings) == 1
    assert findings[0].rule_id == "STAFF-INVALID-PROJECT"


# ── check_authorization ──────────────────────────────────────


class _FakeAssetEntry:
    def __init__(self, entry_id, asset_name, metadata_json):
        self.id = entry_id
        self.asset_name = asset_name
        self.metadata_json = metadata_json


def test_check_authorization_returns_p0_when_no_auth_assets():
    project_id = str(uuid.uuid4())
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_bid_asset_pool_entries",
            return_value=[],
        ):
            findings = check_authorization(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    assert len(findings) == 1
    assert findings[0].severity == "P0"
    assert findings[0].rule_id == "AUTH-MISSING"


def test_check_authorization_detects_missing_phrases():
    project_id = str(uuid.uuid4())
    entries = [
        _FakeAssetEntry(
            "e-1", "授权委托书",
            {"asset_type": "authorization", "content_text": "本授权书由公章确认"},
        ),
    ]
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_bid_asset_pool_entries",
            return_value=entries,
        ):
            findings = check_authorization(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    # Missing "法定代表人" but has "公章"
    incomplete = [f for f in findings if "AUTH-INCOMPLETE" in f.rule_id]
    assert len(incomplete) == 1
    assert "法定代表人" in incomplete[0].message


def test_check_authorization_passes_when_complete():
    project_id = str(uuid.uuid4())
    entries = [
        _FakeAssetEntry(
            "e-1", "授权委托书",
            {"asset_type": "authorization", "content_text": "法定代表人授权并加盖公章"},
        ),
    ]
    with patch("app.db.session.session_scope") as mock_scope:
        mock_db = mock_scope.return_value.__enter__.return_value
        with patch(
            "app.tender.assets.repository.list_bid_asset_pool_entries",
            return_value=entries,
        ):
            findings = check_authorization(
                project_id=project_id,
                tender_package_id="pkg-1",
            )
    assert len(findings) == 0


# ── Integration: run_redline_check with active checks ────────


def test_run_redline_check_with_active_checks_disabled():
    payload = RedlineCheckRequest(
        project_id="proj-1",
        tender_package_id="pkg-1",
        run_active_checks=False,
    )
    report = run_redline_check(payload)
    assert report.status == "PASS"
    assert len(report.findings) == 0


def test_run_redline_check_merges_active_check_findings():
    with (
        patch(
            "app.services.redline_engine.check_qualifications",
            return_value=[
                RedlineFinding(rule_id="QUAL-MISSING", category="资质", severity="P0", message="no quals"),
            ],
        ),
        patch("app.services.redline_engine.check_key_staff_and_ss", return_value=[]),
        patch("app.services.redline_engine.check_authorization", return_value=[]),
    ):
        payload = RedlineCheckRequest(
            project_id="proj-1",
            tender_package_id="pkg-1",
            run_active_checks=True,
        )
        report = run_redline_check(payload)

    assert report.status == "BLOCKED"
    assert any(f.rule_id == "QUAL-MISSING" for f in report.findings)
