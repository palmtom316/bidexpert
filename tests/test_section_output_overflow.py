"""Tests for W1-4: long section output tolerance.

TDD RED phase: verifies that the token gate allows controlled overflow
instead of hard-failing with NEED_HUMAN_INPUT.
"""
from __future__ import annotations



class TestSectionOutputOverflowConfig:
    """Config should have overflow factor setting."""

    def test_overflow_factor_exists(self):
        from app.core.config import settings
        assert hasattr(settings, "section_output_overflow_factor")

    def test_overflow_factor_default(self):
        from app.core.config import settings
        assert settings.section_output_overflow_factor >= 1.5


class TestTokenGateSoftWarning:
    """Token gate should allow moderate overflow with warning, not hard-fail."""

    def test_section_output_limit_with_overflow(self):
        from app.core.config import get_section_max_output_tokens, settings
        base_limit = get_section_max_output_tokens("construction_plan")
        factor = settings.section_output_overflow_factor
        assert base_limit * factor > base_limit

    def test_effective_limit_function_exists(self):
        """Pipeline should expose a function to compute effective limit with overflow."""
        from app.services.generation_pipeline import _effective_section_output_limit
        limit = _effective_section_output_limit({"section_type": "construction_plan"})
        # Should be base_limit * overflow_factor
        from app.core.config import get_section_max_output_tokens, settings
        base = get_section_max_output_tokens("construction_plan")
        expected = int(base * settings.section_output_overflow_factor)
        assert limit == expected

    def test_effective_limit_default_section(self):
        from app.services.generation_pipeline import _effective_section_output_limit
        from app.core.config import get_section_max_output_tokens, settings
        limit = _effective_section_output_limit(None)
        base = get_section_max_output_tokens(None)
        expected = int(base * settings.section_output_overflow_factor)
        assert limit == expected
