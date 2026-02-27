from __future__ import annotations

from dataclasses import dataclass

from app.services.adapters.ocr import OCRRuntimeCredential, create_ocr_adapter


@dataclass
class _DummyResponse:
    payload: dict

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_mineru_adapter_prefers_runtime_credential(monkeypatch) -> None:
    from app.services.adapters import ocr as ocr_module

    monkeypatch.setattr(ocr_module.settings, "mineru_ocr_api_key", "env-key", raising=False)
    monkeypatch.setattr(ocr_module.settings, "mineru_ocr_base_url", "https://env-mineru/v1", raising=False)
    monkeypatch.setattr(ocr_module.settings, "mineru_ocr_model", "env-model", raising=False)

    captured: dict[str, object] = {}

    class _DummyClient:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, D401
            pass

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:  # noqa: ANN001, D401
            return False

        def post(self, url: str, headers: dict, json: dict) -> _DummyResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _DummyResponse(payload={"choices": [{"message": {"content": "mineru text"}}]})

    monkeypatch.setattr(ocr_module.httpx, "Client", _DummyClient)
    adapter = create_ocr_adapter(
        "mineru",
        runtime_credential=OCRRuntimeCredential(
            api_key="runtime-key",
            base_url="https://runtime-mineru/v1",
            model="runtime-model",
        ),
    )
    text = adapter.extract_image_bytes(b"img")

    assert text == "mineru text"
    assert captured["url"] == "https://runtime-mineru/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer runtime-key", "Content-Type": "application/json"}
    body = captured["json"]
    assert isinstance(body, dict)
    assert body["model"] == "runtime-model"
