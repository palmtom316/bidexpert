from __future__ import annotations

from app.services import context_compressor



def test_context_compressor_prefers_llm_output_when_available(monkeypatch) -> None:
    monkeypatch.setattr(context_compressor.settings, "context_compression_use_llm", True, raising=False)
    monkeypatch.setattr(
        context_compressor,
        "_compress_with_llm",
        lambda **_: ["证据片段A", "证据片段B"],
    )

    result = context_compressor.compress_evidence_context(
        requirement_text="必须具备相关业绩",
        evidence_texts=["证据1", "证据2", "证据3"],
    )

    assert result.evidence_texts == ["证据片段A", "证据片段B"]
    assert result.dropped_count == 1



def test_context_compressor_falls_back_when_llm_has_no_output(monkeypatch) -> None:
    monkeypatch.setattr(context_compressor.settings, "context_compression_use_llm", True, raising=False)
    monkeypatch.setattr(context_compressor, "_compress_with_llm", lambda **_: [])

    result = context_compressor.compress_evidence_context(
        requirement_text="必须具备相关业绩",
        evidence_texts=["证据1内容较长", "证据2内容较长"],
    )

    assert len(result.evidence_texts) >= 1
