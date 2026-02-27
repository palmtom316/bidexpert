from __future__ import annotations

from pathlib import Path

import pytest

from app.services.expert_library import (
    get_expert_library_go_live_thresholds,
    get_expert_library_thresholds,
    publish_expert_library_go_live_thresholds,
    update_expert_library_go_live_thresholds,
    update_expert_library_thresholds,
)


def test_update_expert_library_thresholds_writes_runtime_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.expert_library.settings.expert_library_root", str(tmp_path), raising=False)

    updated = update_expert_library_thresholds(
        {
            "low_confidence": 0.66,
            "strong_review_confidence": 0.82,
            "max_section_pages": 24,
        }
    )
    values = updated["values"]
    assert values["low_confidence"] == 0.66
    assert values["strong_review_confidence"] == 0.82
    assert values["max_section_pages"] == 24

    runtime_path = Path(updated["source"]["runtime_path"])
    assert runtime_path.exists()
    content = runtime_path.read_text(encoding="utf-8")
    assert "low_confidence: 0.66" in content
    assert "strong_review_confidence: 0.82" in content

    loaded = get_expert_library_thresholds()
    assert loaded["values"]["low_confidence"] == 0.66
    assert loaded["values"]["strong_review_confidence"] == 0.82


def test_go_live_thresholds_save_and_publish(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.expert_library.settings.expert_library_root", str(tmp_path), raising=False)

    saved = update_expert_library_go_live_thresholds(
        {
            "low_confidence": 0.71,
            "strong_review_confidence": 0.88,
        }
    )
    go_live_path = Path(saved["source"]["go_live_path"])
    assert go_live_path.exists()
    go_live_text = go_live_path.read_text(encoding="utf-8")
    assert "low_confidence: 0.71" in go_live_text
    assert "strong_review_confidence: 0.88" in go_live_text

    loaded_go_live = get_expert_library_go_live_thresholds()
    assert loaded_go_live["values"]["low_confidence"] == 0.71
    assert loaded_go_live["values"]["strong_review_confidence"] == 0.88

    published = publish_expert_library_go_live_thresholds()
    runtime_path = Path(published["source"]["runtime_path"])
    assert runtime_path.exists()
    runtime_text = runtime_path.read_text(encoding="utf-8")
    assert "low_confidence: 0.71" in runtime_text
    assert "strong_review_confidence: 0.88" in runtime_text


def test_publish_go_live_thresholds_requires_saved_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("app.services.expert_library.settings.expert_library_root", str(tmp_path), raising=False)
    with pytest.raises(ValueError, match="go_live thresholds not found"):
        publish_expert_library_go_live_thresholds()
