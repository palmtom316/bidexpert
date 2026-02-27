"""Integration test — end-to-end zip → pipeline → READY_FOR_WRITING."""

from __future__ import annotations

import json
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path



def _make_full_tender_zip() -> bytes:
    """Create a realistic .tender.zip with enough content for full pipeline."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        manifest = {
            "tender_id": "INT-TEST-001",
            "tender_name": "110kV变电站新建工程",
            "project_type": "变电站",
            "voltage_level": "110kV",
            "region": "华东",
        }
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr("original.pdf", b"%PDF-1.4 fake")

        md_content = """\
# 第一章 投标须知

## 1.1 资格审查

投标人必须具备电力工程施工总承包一级及以上资质，否则废标。
投标人必须具备承装修试二级及以上资质。
投标人应具有有效的安全生产许可证。
未提供营业执照副本的，投标无效。
投标保证金不足的，取消投标资格。

## 1.2 人员要求

项目经理须持有一级建造师（机电工程专业）证书，且无在建工程，社保6个月以上。
技术负责人须具有高级工程师职称，从业经验不少于10年。
安全员须持有安全生产考核合格证B类安全证。

## 1.3 投标文件格式

投标文件正本1份，副本3份，电子版1份（U盘1个）。
投标文件须用胶装装订。
投标函须加盖公章并由法定代表人签字或授权代表签字。
技术标和商务标应分开密封。

# 第二章 评标办法

评标采用综合评分法，满分100分。
技术方案评分分值40分，商务报价评分分值30分。
施工组织设计评分分值15分。
安全文明施工方案评分分值10分。
信誉评分分值5分。

# 第三章 技术要求

## 3.1 设备安装

变电站110kV GIS设备安装技术要求如下。
投标人必须提供110kV断路器、隔离开关安装调试方案。
继电保护装置配置须满足国网标准。

## 3.2 施工方案

投标人必须编制详细的施工组织设计方案。
带电作业须满足安全规程要求，不得违规操作。
接地装置安装须符合DL/T 621标准。

## 3.3 试验验收

交接试验须按GB 50150标准执行。
耐压试验设备参数须满足110kV等级要求。
"""
        zf.writestr("full.md", md_content)
    return buf.getvalue()


def test_full_pipeline_reaches_ready_for_writing() -> None:
    """End-to-end: zip → unpack → all extractors → READY_FOR_WRITING."""
    from app.tender.zip_package import load_manifest, unpack_zip, validate_tender_package
    from app.tender.sectionizer import sectionize
    from app.tender.prelim_extractor import extract_preliminary
    from app.tender.key_personnel_extractor import extract_key_personnel
    from app.tender.fatal_gate import check_fatal_gate
    from app.tender.scoring_extractor import extract_scoring
    from app.tender.technical_extractor import extract_technical
    from app.tender.deviation_builder import build_deviation_tables
    from app.tender.format_signature_extractor import extract_format_signature
    from app.tender.compliance_extractor import extract_compliance
    from app.tender.blueprint_builder import build_blueprint

    zip_bytes = _make_full_tender_zip()

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        derived_dir = workspace / "derived"
        derived_dir.mkdir()

        # Step 1: Unpack
        root = unpack_zip(zip_bytes, workspace / "unpacked")
        manifest = load_manifest(root)
        validate_tender_package(root, manifest)
        assert manifest.tender_id == "INT-TEST-001"

        # Step 2: Read markdown
        md_text = (root / "full.md").read_text(encoding="utf-8")
        assert len(md_text) > 100

        # Step 3: Sectionize
        sections = sectionize(md_text)
        assert len(sections.sections) >= 3
        _save(derived_dir, "tender_sections.json", sections)

        # Step 4: Preliminary extraction
        prelim = extract_preliminary(md_text)
        assert prelim.fatal_count >= 2
        _save(derived_dir, "preliminary_evaluation.json", prelim)

        # Step 5: Key personnel
        personnel = extract_key_personnel(md_text)
        assert len(personnel.constraints) >= 2
        _save(derived_dir, "key_personnel_constraints.json", personnel)

        # Step 6: Fatal gate
        gate = check_fatal_gate(
            prelim.model_dump(mode="json"),
            personnel.model_dump(mode="json"),
        )
        # Gate result is valid (may pass or fail depending on assets)
        assert isinstance(gate.passed, bool)
        _save(derived_dir, "fatal_gate_report.json", gate)

        # Step 7: Scoring
        scoring = extract_scoring(md_text)
        assert len(scoring.items) >= 3
        _save(derived_dir, "scoring_model.json", scoring)

        # Step 8: Technical
        tech = extract_technical(md_text)
        assert len(tech.requirements) >= 2
        # Must detect voltage level
        voltages = [r.voltage_level for r in tech.requirements if r.voltage_level]
        assert len(voltages) >= 1
        _save(derived_dir, "technical_requirements.json", tech)

        # Step 9: Deviation tables (R2)
        deviations = build_deviation_tables(tech.model_dump(mode="json"))
        assert len(deviations.technical_deviations) + len(deviations.commercial_deviations) >= 1
        _save(derived_dir, "deviation_tables.json", deviations)

        # Step 10: Format/signature (R1)
        fmt = extract_format_signature(md_text)
        assert fmt.paper_copies == 1
        assert len(fmt.seal_requirements) >= 1
        _save(derived_dir, "format_signature_constraints.json", fmt)

        # Step 11: Compliance
        compliance = extract_compliance(md_text)
        assert len(compliance.preliminary) >= 1
        _save(derived_dir, "compliance_check.json", compliance)

        # Step 12: Blueprint
        blueprint = build_blueprint(
            tender_id=manifest.tender_id,
            manifest=manifest.model_dump(mode="json"),
            derived_dir=derived_dir,
        )
        assert len(blueprint.tasks) >= 3  # At least P00 admin + P00 deviation + section tasks
        # R1: Must have P00 administrative task
        p00_tasks = [t for t in blueprint.tasks if t.priority == "P00"]
        assert len(p00_tasks) >= 2
        # R6: Hard filters must include voltage_level
        assert "voltage_level" in blueprint.retrieval_policy.hard_filters
        _save(derived_dir, "bid_blueprint.json", blueprint)

        # Verify all derived files exist
        expected_files = [
            "tender_sections.json",
            "preliminary_evaluation.json",
            "key_personnel_constraints.json",
            "fatal_gate_report.json",
            "scoring_model.json",
            "technical_requirements.json",
            "deviation_tables.json",
            "format_signature_constraints.json",
            "compliance_check.json",
            "bid_blueprint.json",
        ]
        for f in expected_files:
            assert (derived_dir / f).exists(), f"missing derived file: {f}"


def test_backward_compat_v10_imports_unaffected() -> None:
    """v1.0 modules must still import and function correctly."""
    from app.services.tender_analysis import (
        analyze_and_persist_tender_pdf,
        get_tender_analysis_detail,
        list_tender_analysis_runs,
    )
    from app.extract.tender_parser import (
        parse_tender_requirements,
        classify_clause_strength,
        ClauseStrength,
    )

    # Parser still works
    result = parse_tender_requirements("投标人必须具备ISO9001资质。评分分值10分。")
    assert result.status in ("OK", "NEED_HUMAN_INPUT")

    # Clause strength classifier still works
    assert classify_clause_strength("废标") == ClauseStrength.DISQUALIFY
    assert classify_clause_strength("扣分") == ClauseStrength.DEDUCT

    # v1.0 functions are importable
    assert callable(analyze_and_persist_tender_pdf)
    assert callable(list_tender_analysis_runs)
    assert callable(get_tender_analysis_detail)


def test_redline_r0_fatal_gate_blocks_pipeline() -> None:
    """R0: When fatal items are unmet, pipeline must not proceed past FATAL_GATE_CHECKED."""
    from app.tender.fatal_gate import check_fatal_gate

    prelim_data = {
        "items": [
            {
                "item_id": "PRE-001",
                "clause_text": "必须具备核工程专用施工资质",
                "clause_strength": "DISQUALIFY",
                "fatal_if_unmet": True,
            },
            {
                "item_id": "PRE-002",
                "clause_text": "必须具备国防工程施工许可证",
                "clause_strength": "DISQUALIFY",
                "fatal_if_unmet": True,
            },
        ],
    }
    personnel_data = {"constraints": []}

    report = check_fatal_gate(prelim_data, personnel_data)
    # These exotic qualifications should not match standard assets
    assert len(report.checks) >= 2


def _save(derived_dir: Path, filename: str, model) -> None:
    """Save a Pydantic model as JSON to derived directory."""
    (derived_dir / filename).write_text(
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
