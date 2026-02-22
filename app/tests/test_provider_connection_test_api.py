from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api import routes
from app.schemas.contracts import OCRConnectionTestRequest, ProviderConnectionTestRequest


def test_provider_connection_test_api_route(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_test_provider_connection(**kwargs):
        captured.update(kwargs)
        return True, "completion probe OK (200)"

    monkeypatch.setattr(routes, "test_provider_connection", _fake_test_provider_connection)

    payload = ProviderConnectionTestRequest(
        provider="qwen",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        default_model="qwen3",
        api_key="sk-test",
    )
    resp = routes.test_provider_connection_api(payload)

    assert resp.ok is True
    assert resp.provider == "qwen"
    assert resp.model == "qwen3"
    assert "completion probe OK" in resp.detail
    assert captured["provider"] == "qwen"
    assert captured["default_model"] == "qwen3"
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


def test_provider_connection_test_api_route_returns_bad_request(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "test_provider_connection",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid provider")),
    )

    payload = ProviderConnectionTestRequest(
        provider="invalid",
        base_url="https://example.ai/v1",
        default_model="x",
        api_key="sk-test",
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.test_provider_connection_api(payload)

    assert exc_info.value.status_code == 400
    assert "invalid provider" in str(exc_info.value.detail)


def test_ocr_connection_test_api_route(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_test_ocr_connection(**kwargs):
        captured.update(kwargs)
        return "textin", "app-id-1", True, "textin probe OK (200)"

    monkeypatch.setattr(routes, "test_ocr_connection", _fake_test_ocr_connection)

    payload = OCRConnectionTestRequest(
        provider="textin",
        base_url="https://api.textin.com/ai/service/v2/recognize/document",
        model="app-id-1",
        api_key="secret-code",
    )
    resp = routes.test_ocr_connection_api(payload)

    assert resp.ok is True
    assert resp.provider == "textin"
    assert resp.model == "app-id-1"
    assert "probe OK" in resp.detail
    assert captured["provider"] == "textin"
    assert captured["model"] == "app-id-1"


def test_ocr_connection_test_api_route_returns_bad_request(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "test_ocr_connection",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("unsupported ocr provider")),
    )

    payload = OCRConnectionTestRequest(
        provider="hunyuan",
        base_url="https://example.ai/ocr",
        model="any",
        api_key="secret",
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.test_ocr_connection_api(payload)

    assert exc_info.value.status_code == 400
    assert "unsupported ocr provider" in str(exc_info.value.detail)
