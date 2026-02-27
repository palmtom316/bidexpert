"""Tests for G8 knowledge feedback logic."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import tables  # noqa: F401
from app.models.tables import CompletedBid, EvidenceChunk, ExpertDoc, Project
from app.services.completed_bids import (
    get_feedback_eligible_bids,
    ingest_completed_bid_to_knowledge_base,
)


def _setup_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    return engine


def _patch_session_scope(monkeypatch, engine):
    from contextlib import contextmanager

    @contextmanager
    def _test_session_scope():
        with Session(engine) as db:
            yield db

    monkeypatch.setattr("app.services.completed_bids.session_scope", _test_session_scope)


def _create_bid(db, project_id, *, project_name="Test Project", bid_result="WON"):
    bid = CompletedBid(
        project_id=project_id,
        project_name=project_name,
        bid_result=bid_result,
        file_name="test.pdf",
        engineering_category="变电工程",
        tenderer="测试公司",
        created_by="test",
    )
    db.add(bid)
    db.flush()
    return bid


def test_get_feedback_eligible_bids_returns_won_only(monkeypatch):
    engine = _setup_db()
    _patch_session_scope(monkeypatch, engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        _create_bid(db, project.id, project_name="Won Bid", bid_result="WON")
        _create_bid(db, project.id, project_name="Lost Bid", bid_result="LOST")
        db.commit()

    eligible = get_feedback_eligible_bids()
    assert len(eligible) == 1
    assert eligible[0].bid_result == "WON"
    assert eligible[0].project_name == "Won Bid"


def test_get_feedback_eligible_bids_empty(monkeypatch):
    engine = _setup_db()
    _patch_session_scope(monkeypatch, engine)

    eligible = get_feedback_eligible_bids()
    assert len(eligible) == 0


def test_ingest_completed_bid_creates_expert_doc_and_chunk(monkeypatch):
    engine = _setup_db()
    _patch_session_scope(monkeypatch, engine)

    with Session(engine) as db:
        project = Project(name="P", owner_user_id="u")
        db.add(project)
        db.flush()

        bid = _create_bid(db, project.id, project_name="中标项目A", bid_result="WON")
        db.commit()
        bid_id = str(bid.id)

    result = ingest_completed_bid_to_knowledge_base(bid_id)

    assert result["status"] == "ingested"
    assert result["chunks_created"] == 1

    with Session(engine) as db:
        doc = db.execute(
            select(ExpertDoc).where(ExpertDoc.doc_type == "COMPLETED_BID_FEEDBACK")
        ).scalar_one()
        assert "中标项目A" in doc.title

        chunk = db.execute(
            select(EvidenceChunk).where(EvidenceChunk.expert_doc_id == doc.id)
        ).scalar_one()
        assert "中标项目A" in chunk.excerpt_text
        assert "变电工程" in chunk.excerpt_text


def test_ingest_completed_bid_invalid_id_raises(monkeypatch):
    engine = _setup_db()
    _patch_session_scope(monkeypatch, engine)

    with pytest.raises(ValueError, match="invalid record_id"):
        ingest_completed_bid_to_knowledge_base("not-a-uuid")


def test_ingest_completed_bid_not_found_raises(monkeypatch):
    engine = _setup_db()
    _patch_session_scope(monkeypatch, engine)

    with pytest.raises(ValueError, match="not found"):
        ingest_completed_bid_to_knowledge_base(str(uuid.uuid4()))
