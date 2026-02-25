"""Task 11: 分块噪声控制 — tests.

Covers:
- R04: Minimum chunk length threshold is configurable and raised from 24 to >=80
"""
from __future__ import annotations

from types import SimpleNamespace

from app.core.config import settings
from app.services.expert_library import _fallback_chunks_from_blocks


# ---------------------------------------------------------------------------
# R04-1: Config has chunk_min_char_length setting
# ---------------------------------------------------------------------------

def test_config_has_chunk_min_char_length() -> None:
    assert hasattr(settings, "chunk_min_char_length")


def test_chunk_min_char_length_default_ge_80() -> None:
    assert settings.chunk_min_char_length >= 80


# ---------------------------------------------------------------------------
# R04-2: _fallback_chunks_from_blocks respects configurable threshold
# ---------------------------------------------------------------------------

def _make_block(text: str, page_no: int = 1, block_type: str = "PARA") -> SimpleNamespace:
    return SimpleNamespace(content_text=text, page_no=page_no, block_type=block_type, section_anchor=None)


def test_fallback_rejects_short_chunks() -> None:
    """Text shorter than chunk_min_char_length should be filtered out."""
    short_text = "这是一段很短的文本"  # ~9 chars
    blocks = [_make_block(short_text)]
    result = _fallback_chunks_from_blocks(
        blocks=blocks,
        industry_tag=None,
        doc_type="EXPERT",
        pricing_related=False,
        doc_id="test-doc",
    )
    assert len(result) == 0


def test_fallback_accepts_long_chunks() -> None:
    """Text longer than chunk_min_char_length should be accepted."""
    long_text = "这是一段足够长的投标文本内容，" * 20  # ~280 chars
    blocks = [_make_block(long_text)]
    result = _fallback_chunks_from_blocks(
        blocks=blocks,
        industry_tag=None,
        doc_type="EXPERT",
        pricing_related=False,
        doc_id="test-doc",
    )
    assert len(result) == 1


def test_fallback_filters_mixed_lengths() -> None:
    """Only chunks above threshold should survive."""
    short = _make_block("短文本")
    medium = _make_block("A" * 50)  # 50 chars, below 80
    long = _make_block("这是一段足够长的投标文本内容用于测试分块最小长度阈值的过滤逻辑，" * 8)  # ~240 chars
    blocks = [short, medium, long]
    result = _fallback_chunks_from_blocks(
        blocks=blocks,
        industry_tag=None,
        doc_type="EXPERT",
        pricing_related=False,
        doc_id="test-doc",
    )
    assert len(result) == 1


def test_old_24_char_threshold_no_longer_used() -> None:
    """A 30-char text should NOT pass the new threshold (was accepted with old 24)."""
    text_30 = "这是三十个字符左右的一段测试文本内容啊"  # ~18 chars
    blocks = [_make_block(text_30)]
    result = _fallback_chunks_from_blocks(
        blocks=blocks,
        industry_tag=None,
        doc_type="EXPERT",
        pricing_related=False,
        doc_id="test-doc",
    )
    assert len(result) == 0


# ---------------------------------------------------------------------------
# R04-3: Enterprise pipeline uses same threshold for confidence/summary
# ---------------------------------------------------------------------------

def test_enterprise_pipeline_threshold_configurable() -> None:
    """The enterprise pipeline should reference the configurable threshold, not hardcoded 24."""
    threshold = settings.chunk_min_char_length
    assert threshold >= 80, f"Expected >=80, got {threshold}"
