from __future__ import annotations

import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings

OCR_PROVIDER_ALLOWLIST = frozenset({"glm-ocr", "textin", "tesseract", "local", "hunyuan", "docai", ""})
_OCR_PROVIDER_ALIASES = {
    "glmocr": "glm-ocr",
    "glm_ocr": "glm-ocr",
    "text-in": "textin",
    "text_in": "textin",
}
TEXTIN_OCR_ENDPOINT_DEFAULT = "https://api.textin.com/ai/service/v2/recognize/document"


class OCRAdapterUnavailableError(RuntimeError):
    pass


class OCRAdapter(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:
        raise NotImplementedError


@dataclass(frozen=True)
class OCRPageResult:
    page_no: int
    text: str
    confidence: float = 1.0


@dataclass(frozen=True)
class OCRRuntimeCredential:
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


def normalize_ocr_provider(provider: str | None, *, default: str | None = None) -> str:
    raw = provider if provider is not None else default
    normalized = str(raw or "").strip().lower().replace("_", "-")
    normalized = _OCR_PROVIDER_ALIASES.get(normalized, normalized)
    if normalized not in OCR_PROVIDER_ALLOWLIST:
        raise ValueError(f"unsupported ocr provider: {normalized}")
    return normalized


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


def _extract_textin_ocr_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    result = payload.get("result")
    if not isinstance(result, dict):
        return ""

    direct = result.get("text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    lines = result.get("lines")
    if isinstance(lines, list):
        merged = [str(item.get("text", "")).strip() for item in lines if isinstance(item, dict) and str(item.get("text", "")).strip()]
        if merged:
            return "\n".join(merged)

    pages = result.get("pages")
    if isinstance(pages, list):
        merged_lines: list[str] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_lines = page.get("lines")
            if not isinstance(page_lines, list):
                continue
            merged_lines.extend(
                str(item.get("text", "")).strip()
                for item in page_lines
                if isinstance(item, dict) and str(item.get("text", "")).strip()
            )
        if merged_lines:
            return "\n".join(merged_lines)
    return ""


class TextInOCRAdapter(OCRAdapter):
    provider = "textin"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.secret_code = (api_key if api_key is not None else settings.textin_ocr_api_key or "").strip()
        self.base_url = (
            base_url
            if base_url is not None
            else settings.textin_ocr_base_url or TEXTIN_OCR_ENDPOINT_DEFAULT
        ).strip()
        self.app_id = (model if model is not None else settings.textin_ocr_model or "").strip()

    def _require_credential(self) -> None:
        if not self.secret_code or not self.base_url or not self.app_id:
            raise OCRAdapterUnavailableError(f"{self.provider} ocr credential is not configured")

    def extract(self, file_path: str) -> dict[str, Any]:
        with open(file_path, "rb") as handle:
            text = self.extract_image_bytes(handle.read())
        return {"text": text}

    def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:  # noqa: ARG002
        self._require_credential()
        timeout = httpx.Timeout(float(settings.llm_http_timeout_seconds))
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    self.base_url,
                    headers={
                        "x-ti-app-id": self.app_id,
                        "x-ti-secret-code": self.secret_code,
                        "Content-Type": "application/octet-stream",
                    },
                    content=image_bytes,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise OCRAdapterUnavailableError(f"{self.provider} ocr request failed") from exc

        text = _extract_textin_ocr_text(payload)
        if text:
            return text
        raise OCRAdapterUnavailableError(f"{self.provider} ocr response is invalid")


def _extract_chat_content_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        lines: list[str] = []
        for item in content:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    lines.append(text)
                continue
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                lines.append(text.strip())
                continue
            fallback = item.get("content")
            if isinstance(fallback, str) and fallback.strip():
                lines.append(fallback.strip())
        return "\n".join(lines).strip()
    return ""


class GLMOCRAdapter(OCRAdapter):
    provider = "glm-ocr"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = (api_key if api_key is not None else settings.glm_ocr_api_key or "").strip()
        self.base_url = (base_url if base_url is not None else settings.glm_ocr_base_url or "").strip()
        self.model = (model if model is not None else settings.glm_ocr_model or "glm-ocr").strip() or "glm-ocr"

    def _require_credential(self) -> None:
        if not self.api_key or not self.base_url:
            raise OCRAdapterUnavailableError(f"{self.provider} ocr credential is not configured")

    def extract(self, file_path: str) -> dict[str, Any]:
        with open(file_path, "rb") as handle:
            text = self.extract_image_bytes(handle.read())
        return {"text": text}

    def extract_image_bytes(self, image_bytes: bytes, page_no: int | None = None) -> str:  # noqa: ARG002
        self._require_credential()
        timeout = httpx.Timeout(float(settings.llm_http_timeout_seconds))
        encoded = base64.b64encode(image_bytes).decode("ascii")
        endpoint = f"{self.base_url.rstrip('/')}/chat/completions"
        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "请识别图片中的文字并尽量保持段落/列表结构，只输出文本。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                    ],
                }
            ],
            "temperature": 0,
        }
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise OCRAdapterUnavailableError(f"{self.provider} ocr request failed") from exc

        if isinstance(payload, dict):
            choices = payload.get("choices")
            if isinstance(choices, list) and choices:
                first = choices[0]
                if isinstance(first, dict):
                    message = first.get("message")
                    if isinstance(message, dict):
                        text = _extract_chat_content_text(message.get("content"))
                        if text:
                            return text
        raise OCRAdapterUnavailableError(f"{self.provider} ocr response is invalid")


def test_ocr_connection(
    *,
    provider: str,
    api_key: str,
    base_url: str | None = None,
    model: str | None = None,
) -> tuple[str, str, bool, str]:
    normalized = normalize_ocr_provider(provider, default=settings.ocr_provider or "glm-ocr")
    if normalized not in {"glm-ocr", "textin"}:
        raise ValueError(f"unsupported ocr provider: {normalized}")

    effective_model = (model or "").strip() or ("your-textin-app-id" if normalized == "textin" else "glm-ocr")
    credential = (api_key or "").strip()
    if not credential:
        return normalized, effective_model, False, "missing credential"

    default_base_url = (
        settings.textin_ocr_base_url or TEXTIN_OCR_ENDPOINT_DEFAULT
        if normalized == "textin"
        else settings.glm_ocr_base_url or ""
    )
    effective_base_url = (base_url or "").strip() or str(default_base_url or "").strip()
    if not effective_base_url:
        return normalized, effective_model, False, "missing base_url"

    timeout = float(settings.llm_http_timeout_seconds)
    if normalized == "textin":
        if not (model or "").strip() or effective_model == "your-textin-app-id":
            return normalized, effective_model, False, "missing app_id"
        try:
            response = httpx.post(
                effective_base_url,
                headers={
                    "x-ti-app-id": effective_model,
                    "x-ti-secret-code": credential,
                    "Content-Type": "application/octet-stream",
                },
                content=b"probe",
                timeout=timeout,
            )
            if 200 <= response.status_code < 400:
                return normalized, effective_model, True, f"textin probe OK ({response.status_code})"
            return normalized, effective_model, False, f"textin probe returned {response.status_code}"
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            return normalized, effective_model, False, f"textin probe failed: {exc}"

    endpoint = f"{effective_base_url.rstrip('/')}/chat/completions"
    body = {
        "model": effective_model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
    }
    try:
        response = httpx.post(
            endpoint,
            json=body,
            headers={
                "Authorization": f"Bearer {credential}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        if 200 <= response.status_code < 400:
            return normalized, effective_model, True, f"glm-ocr probe OK ({response.status_code})"
        return normalized, effective_model, False, f"glm-ocr probe returned {response.status_code}"
    except (httpx.HTTPError, OSError, TimeoutError) as exc:
        return normalized, effective_model, False, f"glm-ocr probe failed: {exc}"


def create_ocr_adapter(provider: str | None = None, *, runtime_credential: OCRRuntimeCredential | None = None) -> OCRAdapter:
    normalized = normalize_ocr_provider(provider, default=settings.ocr_provider or "tesseract")
    if normalized == "glm-ocr":
        return GLMOCRAdapter(
            api_key=runtime_credential.api_key if runtime_credential else None,
            base_url=runtime_credential.base_url if runtime_credential else None,
            model=runtime_credential.model if runtime_credential else None,
        )
    if normalized == "textin":
        return TextInOCRAdapter(
            api_key=runtime_credential.api_key if runtime_credential else None,
            base_url=runtime_credential.base_url if runtime_credential else None,
            model=runtime_credential.model if runtime_credential else None,
        )
    if normalized == "hunyuan":
        return HunyuanOCRAdapter()
    if normalized == "docai":
        return DocAIOCRAdapter()
    raise OCRAdapterUnavailableError(f"unsupported ocr provider: {normalized}")
