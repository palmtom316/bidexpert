from __future__ import annotations

import pytest

from app.llm.model_registry import default_model_for_role, get_fallback_chain
from app.llm.roles import ModelRole
from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.registry import create_adapter


def test_generate_role_prefers_qwen35() -> None:
    assert get_fallback_chain(ModelRole.GENERATE)[0] == ("qwen", "qwen3.5")
    assert default_model_for_role(ModelRole.GENERATE) == ("qwen", "qwen3.5")


def test_extract_review_rewrite_roles_prefer_qwen35() -> None:
    assert get_fallback_chain(ModelRole.EXTRACT)[0] == ("qwen", "qwen3.5")
    assert get_fallback_chain(ModelRole.REVIEW)[0] == ("qwen", "qwen3.5")
    assert get_fallback_chain(ModelRole.QUERY_REWRITE)[0] == ("qwen", "qwen3.5")


def test_create_adapter_rejects_unknown_provider() -> None:
    with pytest.raises(AdapterUnavailableError, match="unsupported provider"):
        create_adapter("not-a-provider")
