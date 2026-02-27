from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import BidAssetPool, ChapterEvidenceLink, EvidenceChunk, ExpertDoc, Project
from app.services.entity_assembly import render_bid_asset_pool_markdown_table
from app.services.frozen_block_guard import build_frozen_block_signatures
from app.services.generation_pipeline import persist_chapter_evidence_links
from app.services.word_renderer import render_word_structured


def test_frozen_block_hash_mismatch_blocks_export(tmp_path, monkeypatch) -> None:
    from app.services import word_renderer

    monkeypatch.setattr(word_renderer.settings, "render_template_dir", str(tmp_path / "templates"), raising=False)
    monkeypatch.setattr(word_renderer.settings, "render_output_dir", str(tmp_path / "out"), raising=False)

    original = "[FROZEN:LEGAL]本承诺函内容不得修改[/FROZEN]"
    signatures = build_frozen_block_signatures(original)

    content = {
        "body": [
            {"type": "heading", "style": "Title1", "text": "承诺函"},
            {"type": "paragraph", "style": "BodyText", "text": "[FROZEN:LEGAL]本承诺函内容已被修改[/FROZEN]"},
        ],
        "appendix": [],
    }

    try:
        render_word_structured(
            output_path="frozen/demo.docx",
            content=content,
            placeholders={},
            frozen_signatures=signatures,
        )
        assert False, "expected frozen hash mismatch to block export"
    except ValueError as exc:
        assert "frozen block hash mismatch" in str(exc)


def test_frozen_block_rejects_duplicate_keys() -> None:
    with pytest.raises(ValueError):
        build_frozen_block_signatures(
            "[FROZEN:LEGAL]A[/FROZEN]\n[FROZEN:LEGAL]B[/FROZEN]"
        )


def test_entity_assembly_renders_bid_asset_pool_tables_via_jinja2() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        db.add_all(
            [
                BidAssetPool(
                    project_id=project.id,
                    asset_name="110kV 变电站业绩",
                    ownership_role="leader",
                    metadata_json={"asset_type": "performance", "evidence_refs": ["E-P-1"]},
                ),
                BidAssetPool(
                    project_id=project.id,
                    asset_name="主变压器设备清单",
                    ownership_role="member",
                    metadata_json={"asset_type": "equipment", "evidence_refs": ["E-E-1"]},
                ),
            ]
        )
        db.flush()

        markdown = render_bid_asset_pool_markdown_table(
            db,
            project_id=project.id,
            asset_type="performance",
            ownership_roles=["leader", "member"],
        )

    assert "| 项目名称 | 合同金额(万元) | 工程类型 | 建设单位 | 竣工日期 | 证据 |" in markdown
    assert "110kV 变电站业绩" in markdown
    assert "E-P-1" in markdown


def test_generation_persists_chapter_evidence_links() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        expert_doc = ExpertDoc(doc_type="EXPERT", title="doc", created_by="u")
        db.add(expert_doc)
        db.flush()

        chunk_1 = EvidenceChunk(expert_doc_id=expert_doc.id, chunk_no=1, excerpt_text="evidence-1")
        chunk_2 = EvidenceChunk(expert_doc_id=expert_doc.id, chunk_no=2, excerpt_text="evidence-2")
        db.add_all([chunk_1, chunk_2])
        db.flush()

        inserted = persist_chapter_evidence_links(
            db,
            project_id=project.id,
            chapter_key="CH-1",
            evidence_chunk_ids=[chunk_1.id, chunk_2.id, chunk_1.id],
        )
        inserted_second_time = persist_chapter_evidence_links(
            db,
            project_id=project.id,
            chapter_key="CH-1",
            evidence_chunk_ids=[chunk_1.id, chunk_2.id],
        )
        db.commit()

        rows = db.execute(
            select(ChapterEvidenceLink).where(
                ChapterEvidenceLink.project_id == project.id,
                ChapterEvidenceLink.chapter_key == "CH-1",
            )
        ).scalars().all()

    assert inserted == 2
    assert inserted_second_time == 0
    assert len(rows) == 2
