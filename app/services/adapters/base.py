from __future__ import annotations

from dataclasses import dataclass


class AdapterUnavailableError(RuntimeError):
    pass


@dataclass
class GenerationRequest:
    model: str
    requirement_text: str
    evidence_texts: list[str]
    api_key: str | None
    base_url: str | None


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str


@dataclass
class ReviewRequest:
    model: str
    draft_text: str
    evidence_texts: list[str]
    api_key: str | None
    base_url: str | None


@dataclass
class ReviewResult:
    approved: bool
    issues: list[str]
    provider: str
    model: str


class LLMAdapter:
    provider: str

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        raise NotImplementedError

    def review(self, payload: ReviewRequest) -> ReviewResult:
        raise NotImplementedError
