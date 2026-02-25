"""Unit tests for v1.4 Metadata Auto-Tagging Engine."""
from __future__ import annotations

import pytest

from app.services.metadata_extractor import (
    DocumentMetadata,
    extract_metadata_regex,
)


class TestVoltageExtraction:
    def test_standard_voltages(self):
        text = "本工程为110kV变电站新建项目，涉及变压器安装。"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv == 110

    def test_lowercase_kv(self):
        text = "35kv输电线路改造工程"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv == 35

    def test_uppercase_kv(self):
        text = "220KV电缆敷设"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv == 220

    def test_10kv(self):
        text = "10kV配电工程施工方案"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv == 10

    def test_no_voltage(self):
        text = "这是一个普通的施工方案文档"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv is None

    def test_multiple_voltages_picks_known(self):
        text = "本项目包含110kV和10kV两个电压等级的设备安装"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv in {10, 110}


class TestProjectTypeExtraction:
    def test_xingjian(self):
        text = "110kV变电站新建工程"
        result = extract_metadata_regex(text)
        assert result.project_type == "新建"

    def test_gaizao(self):
        text = "35kV线路改造项目"
        result = extract_metadata_regex(text)
        assert result.project_type == "改造"

    def test_kuojian(self):
        text = "变电站扩建工程施工方案"
        result = extract_metadata_regex(text)
        assert result.project_type == "扩建"

    def test_yekuo(self):
        text = "业扩配电工程投标文件"
        result = extract_metadata_regex(text)
        assert result.project_type == "业扩配电"

    def test_jigai_maps_to_gaizao(self):
        text = "10kV线路技改方案"
        result = extract_metadata_regex(text)
        assert result.project_type == "改造"

    def test_no_project_type(self):
        text = "设备维护手册"
        result = extract_metadata_regex(text)
        assert result.project_type is None


class TestEquipmentExtraction:
    def test_single_equipment(self):
        text = "本工程主要设备为变压器"
        result = extract_metadata_regex(text)
        assert "变压器" in result.core_equipment

    def test_multiple_equipment(self):
        text = "安装变压器、开关柜和电缆等设备"
        result = extract_metadata_regex(text)
        assert "变压器" in result.core_equipment
        assert "开关柜" in result.core_equipment
        assert "电缆" in result.core_equipment

    def test_no_equipment(self):
        text = "项目管理制度文件"
        result = extract_metadata_regex(text)
        assert result.core_equipment == []

    def test_gis_equipment(self):
        text = "采用GIS组合电器方案"
        result = extract_metadata_regex(text)
        assert "GIS" in result.core_equipment


class TestRegionExtraction:
    def test_jiangsu(self):
        text = "江苏省110kV输变电工程"
        result = extract_metadata_regex(text)
        assert result.region == "江苏"

    def test_shandong(self):
        text = "山东地区35kV配电项目"
        result = extract_metadata_regex(text)
        assert result.region == "山东"

    def test_zhejiang_with_suffix(self):
        text = "浙江省电力有限公司"
        result = extract_metadata_regex(text)
        assert result.region == "浙江"

    def test_neimenggu(self):
        text = "内蒙古自治区风电场建设"
        result = extract_metadata_regex(text)
        assert result.region == "内蒙古"

    def test_no_region(self):
        text = "电力工程施工方案"
        result = extract_metadata_regex(text)
        assert result.region is None


class TestDocumentMetadataMerge:
    def test_merge_fills_gaps(self):
        a = DocumentMetadata(voltage_level_kv=110, project_type=None, core_equipment=[], region=None)
        b = DocumentMetadata(voltage_level_kv=None, project_type="新建", core_equipment=["变压器"], region="江苏")
        merged = a.merge(b)
        assert merged.voltage_level_kv == 110
        assert merged.project_type == "新建"
        assert merged.core_equipment == ["变压器"]
        assert merged.region == "江苏"

    def test_merge_keeps_existing(self):
        a = DocumentMetadata(voltage_level_kv=110, project_type="改造", core_equipment=["电缆"], region="山东")
        b = DocumentMetadata(voltage_level_kv=220, project_type="新建", core_equipment=["变压器"], region="江苏")
        merged = a.merge(b)
        assert merged.voltage_level_kv == 110
        assert merged.project_type == "改造"
        assert merged.core_equipment == ["电缆"]
        assert merged.region == "山东"

    def test_has_gaps(self):
        full = DocumentMetadata(voltage_level_kv=110, project_type="新建", core_equipment=["变压器"], region="江苏")
        assert not full.has_gaps()
        partial = DocumentMetadata(voltage_level_kv=110)
        assert partial.has_gaps()

    def test_to_dict(self):
        m = DocumentMetadata(voltage_level_kv=110, project_type="新建", core_equipment=["变压器"], region="江苏")
        d = m.to_dict()
        assert d["voltage_level_kv"] == 110
        assert d["project_type"] == "新建"
        assert d["core_equipment"] == ["变压器"]
        assert d["region"] == "江苏"


class TestCombinedExtraction:
    def test_full_extraction(self):
        text = "江苏省110kV变电站新建工程，主要安装变压器、开关柜及电缆。"
        result = extract_metadata_regex(text)
        assert result.voltage_level_kv == 110
        assert result.project_type == "新建"
        assert "变压器" in result.core_equipment
        assert "开关柜" in result.core_equipment
        assert "电缆" in result.core_equipment
        assert result.region == "江苏"
