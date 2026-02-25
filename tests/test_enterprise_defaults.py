"""Tests for app.services.expert_enterprise_defaults — config file generation."""
from __future__ import annotations

import json

from app.services.expert_enterprise_defaults import (
    DISCIPLINE_ENUM,
    PROJECT_PHASE_ENUM,
    SECTION_META_SCHEMA,
    SECTION_TYPE_ENUM,
    STRUCTURE_SCHEMA,
    TABLE_TYPE_ENUM,
    enterprise_default_files,
)


class TestEnterpriseDefaultFiles:
    def test_returns_dict(self):
        files = enterprise_default_files()
        assert isinstance(files, dict)

    def test_has_enum_files(self):
        files = enterprise_default_files()
        assert "00_config/enums/section_type.v1.yaml" in files
        assert "00_config/enums/discipline.v1.yaml" in files
        assert "00_config/enums/project_phase.v1.yaml" in files
        assert "00_config/enums/table_type.v1.yaml" in files

    def test_has_schema_files(self):
        files = enterprise_default_files()
        assert "00_config/schema/structure.v1.schema.json" in files
        assert "00_config/schema/section_meta.v1.schema.json" in files

    def test_has_prompt_files(self):
        files = enterprise_default_files()
        prompt_keys = [k for k in files if "prompts/" in k]
        assert len(prompt_keys) >= 3

    def test_has_pipeline_config(self):
        files = enterprise_default_files()
        assert "00_config/pipeline/pipeline.v1.yaml" in files
        assert "00_config/pipeline/thresholds.v1.yaml" in files

    def test_schema_json_valid(self):
        files = enterprise_default_files()
        schema_str = files["00_config/schema/structure.v1.schema.json"]
        parsed = json.loads(schema_str)
        assert parsed["title"] == "DocumentStructureV1"

    def test_all_values_are_strings(self):
        files = enterprise_default_files()
        for key, value in files.items():
            assert isinstance(value, str), f"{key} value is not a string"


class TestEnums:
    def test_section_type_has_values(self):
        assert "技术方案" in SECTION_TYPE_ENUM
        assert "商务部分" in SECTION_TYPE_ENUM

    def test_discipline_has_values(self):
        assert "电气" in DISCIPLINE_ENUM
        assert "土建" in DISCIPLINE_ENUM

    def test_project_phase_has_values(self):
        assert "投标文件" in PROJECT_PHASE_ENUM

    def test_table_type_has_values(self):
        assert "设备清单" in TABLE_TYPE_ENUM


class TestSchemas:
    def test_structure_schema_required_fields(self):
        assert "doc_id" in STRUCTURE_SCHEMA["required"]
        assert "sections" in STRUCTURE_SCHEMA["required"]

    def test_section_meta_schema_required_fields(self):
        assert "section_type" in SECTION_META_SCHEMA["required"]
        assert "confidence" in SECTION_META_SCHEMA["required"]
