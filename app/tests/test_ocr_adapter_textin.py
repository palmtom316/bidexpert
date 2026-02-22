from __future__ import annotations

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


def test_textin_adapter_calls_official_document_endpoint(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "textin_ocr_api_key", "secret-code", raising=False)
    monkeypatch.setattr(
        ocr_module.settings,
        "textin_ocr_base_url",
        "https://api.textin.com/ai/service/v2/recognize/document",
        raising=False,
    )
    monkeypatch.setattr(ocr_module.settings, "textin_ocr_model", "app-id-123", raising=False)

    captured: dict[str, object] = {}

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, url: str, headers: dict, content: bytes) -> _DummyResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return _DummyResponse(payload={"result": {"lines": [{"text": "第一行"}, {"text": "第二行"}]}})

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter("textin")
    text = adapter.extract_image_bytes(b"image-bytes")

    assert text == "第一行\n第二行"
    assert captured["url"] == "https://api.textin.com/ai/service/v2/recognize/document"
    assert captured["headers"] == {
        "x-ti-app-id": "app-id-123",
        "x-ti-secret-code": "secret-code",
        "Content-Type": "application/octet-stream",
    }
    assert captured["content"] == b"image-bytes"


def test_textin_adapter_prefers_runtime_credential(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "textin_ocr_api_key", "env-secret", raising=False)
    monkeypatch.setattr(
        ocr_module.settings,
        "textin_ocr_base_url",
        "https://api.textin.com/ai/service/v2/recognize/document",
        raising=False,
    )
    monkeypatch.setattr(ocr_module.settings, "textin_ocr_model", "env-app-id", raising=False)

    captured: dict[str, object] = {}

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, url: str, headers: dict, content: bytes) -> _DummyResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["content"] = content
            return _DummyResponse(payload={"result": {"text": "runtime-textin"}})

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter(
        "textin",
        runtime_credential=OCRRuntimeCredential(
            api_key="runtime-secret",
            base_url="https://api.textin.com/ai/service/v2/recognize/document",
            model="runtime-app-id",
        ),
    )
    text = adapter.extract_image_bytes(b"runtime-image")

    assert text == "runtime-textin"
    assert captured["url"] == "https://api.textin.com/ai/service/v2/recognize/document"
    assert captured["headers"] == {
        "x-ti-app-id": "runtime-app-id",
        "x-ti-secret-code": "runtime-secret",
        "Content-Type": "application/octet-stream",
    }
    assert captured["content"] == b"runtime-image"


def test_textin_adapter_requires_secret_and_appid(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "textin_ocr_api_key", None, raising=False)
    monkeypatch.setattr(ocr_module.settings, "textin_ocr_model", None, raising=False)

    adapter = create_ocr_adapter("textin")
    with pytest.raises(OCRAdapterUnavailableError):
        adapter.extract_image_bytes(b"fake-image")
