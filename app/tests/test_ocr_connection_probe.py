from __future__ import annotations

from dataclasses import dataclass

from app.services.adapters import ocr as ocr_module


@dataclass
class _DummyResponse:
    status_code: int


def test_test_ocr_connection_requires_credential() -> None:
    provider, model, ok, detail = ocr_module.test_ocr_connection(
        provider="glm-ocr",
        api_key="",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4.1v-thinking-flashx",
    )

    assert provider == "glm-ocr"
    assert model == "glm-4.1v-thinking-flashx"
    assert ok is False
    assert detail == "missing credential"


def test_test_ocr_connection_glm_calls_chat_completion(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url: str, *, json: dict, headers: dict, timeout: float) -> _DummyResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _DummyResponse(status_code=200)

    monkeypatch.setattr(ocr_module.httpx, "post", _fake_post)

    provider, model, ok, detail = ocr_module.test_ocr_connection(
        provider="glm-ocr",
        api_key="glm-key",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        model="glm-4.1v-thinking-flashx",
    )

    assert provider == "glm-ocr"
    assert model == "glm-4.1v-thinking-flashx"
    assert ok is True
    assert detail == "glm-ocr probe OK (200)"
    assert captured["url"] == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer glm-key", "Content-Type": "application/json"}
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["model"] == "glm-4.1v-thinking-flashx"


def test_test_ocr_connection_textin_requires_app_id() -> None:
    provider, model, ok, detail = ocr_module.test_ocr_connection(
        provider="textin",
        api_key="secret-code",
        base_url="https://api.textin.com/ai/service/v2/recognize/document",
        model="",
    )

    assert provider == "textin"
    assert model == "your-textin-app-id"
    assert ok is False
    assert detail == "missing app_id"
