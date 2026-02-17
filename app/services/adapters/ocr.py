from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings


class OCRAdapterUnavailableError(RuntimeError):
    pass


class OCRAdapter(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:
        raise NotImplementedError


class _RemoteOCRAdapter(OCRAdapter):
    provider = "remote"

    def __init__(self, *, api_key: str | None, base_url: str | None) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip()

    def _require_credential(self) -> None:
        if not self.api_key or not self.base_url:
            raise OCRAdapterUnavailableError(f"{self.provider} ocr credential is not configured")

    def extract(self, file_path: str) -> dict[str, Any]:
        with open(file_path, "rb") as handle:
            text = self.extract_image_bytes(handle.read())
        return {"text": text}

    def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:
        self._require_credential()
        endpoint = f"{self.base_url.rstrip('/')}/ocr"
        files = {"file": ("page.png", image_bytes, "image/png")}
        data = {"page_no": str(page_no)} if page_no is not None else None
        timeout = httpx.Timeout(float(settings.llm_http_timeout_seconds))
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise OCRAdapterUnavailableError(f"{self.provider} ocr request failed") from exc

        if isinstance(payload, dict):
            text = payload.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
            result = payload.get("result")
            if isinstance(result, dict) and isinstance(result.get("text"), str):
                return str(result["text"]).strip()
        raise OCRAdapterUnavailableError(f"{self.provider} ocr response is invalid")


class HunyuanOCRAdapter(_RemoteOCRAdapter):
    provider = "hunyuan"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.hunyuan_ocr_api_key,
            base_url=settings.hunyuan_ocr_base_url,
        )


class DocAIOCRAdapter(_RemoteOCRAdapter):
    provider = "docai"

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.docai_ocr_api_key,
            base_url=settings.docai_ocr_base_url,
        )


def create_ocr_adapter(provider: str | None = None) -> OCRAdapter:
    normalized = (provider or settings.ocr_provider or "tesseract").strip().lower()
    if normalized == "hunyuan":
        return HunyuanOCRAdapter()
    if normalized == "docai":
        return DocAIOCRAdapter()
    raise OCRAdapterUnavailableError(f"unsupported ocr provider: {normalized}")
