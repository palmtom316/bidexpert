from __future__ import annotations

import json

import pytest

from app.llm import model_registry as registry_module
from app.llm.model_registry import default_model_for_role, get_fallback_chain
from app.llm.roles import ModelRole
from app.services.adapters.base import AdapterUnavailableError
from app.services.adapters.registry import create_adapter


def _clear_registry_cache() -> None:
    registry_module.clear_model_registry_cache()


def test_generate_role_prefers_qwen35() -> None:
    _clear_registry_cache()
    assert get_fallback_chain(ModelRole.GENERATE)[0] == ("qwen", "qwen3.5")
    assert default_model_for_role(ModelRole.GENERATE) == ("qwen", "qwen3.5")


def test_extract_review_rewrite_roles_prefer_qwen35() -> None:
    _clear_registry_cache()
    assert get_fallback_chain(ModelRole.EXTRACT)[0] == ("qwen", "qwen3.5")
    assert get_fallback_chain(ModelRole.REVIEW)[0] == ("qwen", "qwen3.5")
    assert get_fallback_chain(ModelRole.QUERY_REWRITE)[0] == ("qwen", "qwen3.5")


def test_cn_registry_roles_format_via_env_path(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    registry_path = tmp_path / "model_registry.cn.debug.json"
    registry_path.write_text(
        json.dumps(
            {
                "version": "cn-debug-1.0",
                "roles": {
                    "GENERATE": {
                        "primary": {"provider": "qwen", "model": "qwen-plus"},
                        "fallback": [
                            {"provider": "deepseek", "model": "deepseek-reasoner"},
                            {"provider": "glm", "model": "glm-4"},
                        ],
                    }
                },
                "providers": {
                    "qwen": {
                        "base_url_env": "DASHSCOPE_BASE_URL",
                        "api_key_env": "DASHSCOPE_API_KEY",
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("MODEL_REGISTRY_PATH", str(registry_path))
    _clear_registry_cache()

    assert get_fallback_chain(ModelRole.GENERATE) == [
        ("qwen", "qwen-plus"),
        ("deepseek", "deepseek-reasoner"),
        ("glm", "glm-4"),
    ]
    assert default_model_for_role(ModelRole.GENERATE) == ("qwen", "qwen-plus")



def test_create_adapter_rejects_unknown_provider() -> None:
    with pytest.raises(AdapterUnavailableError, match="unsupported provider"):
        create_adapter("not-a-provider")
