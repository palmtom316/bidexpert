from __future__ import annotations

import base64
from dataclasses import dataclass

import pytest

from app.services.adapters.ocr import OCRAdapterUnavailableError, OCRRuntimeCredential, create_ocr_adapter


@dataclass
class _DummyResponse:
    payload: dict

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_glm_ocr_adapter_calls_openai_compatible_chat(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "glm_ocr_api_key", "secret-key", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_base_url", "https://example.ai/v1", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_model", "glm-ocr", raising=False)

    captured: dict[str, object] = {}

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, url: str, headers: dict, json: dict) -> _DummyResponse:  # noqa: A002
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json
            return _DummyResponse(payload={"choices": [{"message": {"content": "识别文本"}}]})

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter("glm-ocr")
    text = adapter.extract_image_bytes(b"fake-image", page_no=3)

    assert text == "识别文本"
    assert captured["url"] == "https://example.ai/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer secret-key", "Content-Type": "application/json"}

    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "glm-ocr"
    assert body["temperature"] == 0
    messages = body["messages"]
    assert isinstance(messages, list) and messages
    content = messages[0]["content"]
    assert isinstance(content, list) and len(content) == 2
    image_url = content[1]["image_url"]["url"]
    expected_suffix = base64.b64encode(b"fake-image").decode("ascii")
    assert image_url.startswith("data:image/png;base64,")
    assert image_url.endswith(expected_suffix)


def test_glm_ocr_adapter_accepts_list_content_response(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "glm_ocr_api_key", "secret-key", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_base_url", "https://example.ai/v1", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_model", "glm-ocr", raising=False)

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, *args, **kwargs) -> _DummyResponse:  # noqa: ANN002, ANN003
            payload = {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"type": "text", "text": "第一行"},
                                {"type": "output_text", "text": "第二行"},
                            ]
                        }
                    }
                ]
            }
            return _DummyResponse(payload=payload)

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter("glm_ocr")

    assert adapter.extract_image_bytes(b"fake-image") == "第一行\n第二行"


def test_glm_ocr_adapter_requires_credentials(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "glm_ocr_api_key", None, raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_base_url", None, raising=False)

    adapter = create_ocr_adapter("glmocr")
    with pytest.raises(OCRAdapterUnavailableError):
        adapter.extract_image_bytes(b"fake-image")


def test_glm_ocr_adapter_prefers_runtime_credential(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "glm_ocr_api_key", "env-key", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_base_url", "https://env.example/v1", raising=False)
    monkeypatch.setattr(ocr_module.settings, "glm_ocr_model", "env-model", raising=False)

    captured: dict[str, object] = {}

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, url: str, headers: dict, json: dict) -> _DummyResponse:  # noqa: A002
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json
            return _DummyResponse(payload={"choices": [{"message": {"content": "runtime-ocr"}}]})

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter(
        "glm-ocr",
        runtime_credential=OCRRuntimeCredential(
            api_key="runtime-key",
            base_url="https://runtime.example/v1",
            model="runtime-model",
        ),
    )
    text = adapter.extract_image_bytes(b"runtime-image")

    assert text == "runtime-ocr"
    assert captured["url"] == "https://runtime.example/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer runtime-key", "Content-Type": "application/json"}
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model"] == "runtime-model"
