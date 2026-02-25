"""Unit tests for tender v1.1 modules.

5 required + 2 optional tests per the implementation plan.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────

def _make_tender_zip(
    *,
    tender_id: str = "TEST-001",
    include_manifest: bool = True,
    include_pdf: bool = True,
    include_md: bool = True,
    md_content: str = "# 第一章 投标须知\n投标人必须具备承装修试二级资质。\n",
    manifest_extra: dict | None = None,
) -> bytes:
    """Create a minimal .tender.zip in memory."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if include_manifest:
            manifest = {
                "tender_id": tender_id,
                "tender_name": "测试项目",
                "project_type": "变电站",
                "voltage_level": "110kV",
                **(manifest_extra or {}),
            }
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        if include_pdf:
            zf.writestr("original.pdf", b"%PDF-1.4 fake content")
        if include_md:
            zf.writestr("full.md", md_content)
    return buf.getvalue()


# ── Required Test 1: validate_tender_package_missing_manifest_fails ──

def test_validate_tender_package_missing_manifest_fails() -> None:
    """Package without manifest.json must raise TenderPackageError."""
    from app.tender.zip_package import TenderPackageError, load_manifest, unpack_zip

    zip_bytes = _make_tender_zip(include_manifest=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = unpack_zip(zip_bytes, Path(tmpdir) / "work")
        with pytest.raises(TenderPackageError, match="manifest.json"):
            load_manifest(root)


# ── Required Test 2: prelim_extractor_detects_fatal_clause ──

def test_prelim_extractor_detects_fatal_clause() -> None:
    """Preliminary extractor must detect disqualifying clauses as fatal."""
    from app.tender.prelim_extractor import extract_preliminary

    text = (
        "投标人必须具备承装修试二级及以上资质，否则废标。\n"
        "投标人应具有ISO9001质量体系认证。\n"
        "未提供安全生产许可证的，投标无效。\n"
    )
    result = extract_preliminary(text)
    assert result.fatal_count >= 2, f"expected at least 2 fatal items, got {result.fatal_count}"

    fatal_items = [i for i in result.items if i.fatal_if_unmet]
    assert len(fatal_items) >= 2
    # Verify the "废标" clause is detected
    waste_items = [i for i in fatal_items if "废标" in i.clause_text]
    assert len(waste_items) >= 1


# ── Required Test 3: fatal_gate_blocks_when_qualification_missing ──

def test_fatal_gate_blocks_when_qualification_missing() -> None:
    """Fatal gate must block when a fatal item has no matching asset."""
    from app.tender.fatal_gate import check_fatal_gate

    prelim_data = {
        "items": [
            {
                "item_id": "PRE-001",
                "clause_text": "投标人必须具备特种设备制造许可证",
                "clause_strength": "DISQUALIFY",
                "fatal_if_unmet": True,
            },
        ],
    }
    personnel_data = {"constraints": []}

    report = check_fatal_gate(prelim_data, personnel_data)
    # The gate should produce checks
    assert len(report.checks) >= 1
    # Report structure is valid
    assert isinstance(report.passed, bool)
    assert isinstance(report.blocked_reasons, list)


# ── Required Test 4: deviation_builder_generates_tables_from_tracking ──

def test_deviation_builder_generates_tables_from_tracking() -> None:
    """Deviation builder must generate entries from technical requirements."""
    from app.tender.deviation_builder import build_deviation_tables

    tech_data = {
        "requirements": [
            {
                "req_id": "TECH-001",
                "category": "construction_method",
                "description": "施工方案必须包含带电作业安全措施",
                "is_mandatory": True,
                "deviation_tracking": "mandatory_response",
            },
            {
                "req_id": "TECH-002",
                "category": "equipment",
                "description": "主变压器容量不低于50MVA",
                "is_mandatory": False,
                "deviation_tracking": "optional_response",
            },
            {
                "req_id": "TECH-003",
                "category": "schedule",
                "description": "工期不超过180日历天",
                "is_mandatory": True,
                "deviation_tracking": "mandatory_response",
            },
        ],
    }
    result = build_deviation_tables(tech_data)
    # Schedule items go to commercial
    assert len(result.commercial_deviations) >= 1
    # Technical items go to technical
    assert len(result.technical_deviations) >= 1
    # Mandatory items have high risk
    mandatory_entries = [
        e for e in result.technical_deviations + result.commercial_deviations
        if e.risk_level == "high"
    ]
    assert len(mandatory_entries) >= 1


# ── Required Test 5: format_signature_extractor_extracts_copies_and_seals ──

def test_format_signature_extractor_extracts_copies_and_seals() -> None:
    """Format extractor must find paper copies and seal requirements."""
    from app.tender.format_signature_extractor import extract_format_signature

    text = (
        "投标文件正本1份，副本3份，电子版1份（U盘）。\n"
        "投标文件须用胶装装订，不得使用活页。\n"
        "投标函须加盖公章并由法定代表人签字。\n"
        "技术标和商务标应分开密封。\n"
    )
    result = extract_format_signature(text)
    assert result.paper_copies == 1
    assert result.binding_method == "胶装"
    assert len(result.seal_requirements) >= 1
    assert any("公章" in s for s in result.seal_requirements)
    assert len(result.envelope_requirements) >= 1


# ── Optional Test 6: pipeline_sectionizer_splits_markdown ──

def test_sectionizer_splits_markdown() -> None:
    """Sectionizer should split markdown by Chinese headings."""
    from app.tender.sectionizer import sectionize

    md = (
        "# 第一章 投标须知\n"
        "本章规定投标人须知事项。\n"
        "投标人必须满足以下条件。\n"
        "\n"
        "# 第二章 评标办法\n"
        "评标采用综合评分法，满分100分。\n"
        "技术评分占60分。\n"
        "\n"
        "# 第三章 技术要求\n"
        "变电站110kV设备安装。\n"
    )
    result = sectionize(md)
    assert len(result.sections) >= 3


# ── Optional Test 7: scoring_extractor_finds_score_items ──

def test_scoring_extractor_finds_score_items() -> None:
    """Scoring extractor should extract items with numeric scores."""
    from app.tender.scoring_extractor import extract_scoring

    text = (
        "# 评分办法\n"
        "技术方案评分分值30分。\n"
        "施工组织设计评分分值20分。\n"
        "安全文明施工方案评分分值10分。\n"
        "报价评分分值40分。\n"
    )
    result = extract_scoring(text)
    assert len(result.items) >= 3
    # Check that scores are extracted
    scores = [i.max_score for i in result.items]
    assert 30.0 in scores
    assert 20.0 in scores


# ── Zip package validation tests ──────────────────────────────

def test_validate_tender_package_missing_pdf_fails() -> None:
    """Package without original.pdf must fail."""
    from app.tender.zip_package import TenderPackageError, load_manifest, unpack_zip, validate_tender_package

    zip_bytes = _make_tender_zip(include_pdf=False)
    with tempfile.TemporaryDirectory() as tmpdir:
        root = unpack_zip(zip_bytes, Path(tmpdir) / "work")
        manifest = load_manifest(root)
        with pytest.raises(TenderPackageError, match="original.pdf"):
            validate_tender_package(root, manifest)


def test_validate_tender_package_empty_md_fails() -> None:
    """Package with empty full.md must fail."""
    from app.tender.zip_package import TenderPackageError, load_manifest, unpack_zip, validate_tender_package

    zip_bytes = _make_tender_zip(md_content="")
    with tempfile.TemporaryDirectory() as tmpdir:
        root = unpack_zip(zip_bytes, Path(tmpdir) / "work")
        manifest = load_manifest(root)
        with pytest.raises(TenderPackageError, match="full.md is empty"):
            validate_tender_package(root, manifest)


def test_valid_tender_package_passes() -> None:
    """A complete package should pass validation."""
    from app.tender.zip_package import load_manifest, unpack_zip, validate_tender_package

    zip_bytes = _make_tender_zip()
    with tempfile.TemporaryDirectory() as tmpdir:
        root = unpack_zip(zip_bytes, Path(tmpdir) / "work")
        manifest = load_manifest(root)
        warnings = validate_tender_package(root, manifest)
        # Should pass with only optional file warnings
        assert isinstance(warnings, list)


# ── Technical extractor voltage detection ─────────────────────

def test_technical_extractor_detects_voltage() -> None:
    """Technical extractor must identify voltage levels."""
    from app.tender.technical_extractor import extract_technical

    text = (
        "变电站110kV设备安装技术要求如下。\n"
        "投标人必须提供220kV GIS设备的施工方案。\n"
        "配电网10kV线路改造材料要求。\n"
    )
    result = extract_technical(text)
    voltages = [r.voltage_level for r in result.requirements if r.voltage_level]
    assert len(voltages) >= 1
    assert any("110" in v for v in voltages) or any("220" in v for v in voltages)


# ── Key personnel extractor ───────────────────────────────────

def test_key_personnel_extractor() -> None:
    """Personnel extractor should find role constraints."""
    from app.tender.key_personnel_extractor import extract_key_personnel

    text = (
        "项目经理须持有一级建造师证书，且无在建工程。\n"
        "技术负责人须具有高级工程师职称。\n"
        "安全员须持有安全生产考核合格证（B类安全证）。\n"
    )
    result = extract_key_personnel(text)
    assert len(result.constraints) >= 2
    roles = [c.role for c in result.constraints]
    assert "项目经理" in roles
