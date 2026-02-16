from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OCRAdapter(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> dict[str, Any]:
        raise NotImplementedError


class HunyuanOCRAdapter(OCRAdapter):
    def extract(self, file_path: str) -> dict[str, Any]:
        raise NotImplementedError("HunyuanOCR adapter not implemented")


class DocAIOCRAdapter(OCRAdapter):
    def extract(self, file_path: str) -> dict[str, Any]:
        raise NotImplementedError("DocAI adapter not implemented")
