from __future__ import annotations

from dataclasses import dataclass


class AdapterUnavailableError(RuntimeError):
    pass


@dataclass
class GenerationRequest:
    model: str
    requirement_text: str
    evidence_texts: list[str]
    evidence_ids: list[str]
    api_key: str | None
    base_url: str | None


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    content_json: dict | None = None


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
    report: dict | None = None


@dataclass
class QueryRewriteRequest:
    model: str
    query: str
    api_key: str | None
    base_url: str | None


@dataclass
class QueryRewriteResult:
    rewritten_query: str
    provider: str
    model: str


class LLMAdapter:
    provider: str

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        raise NotImplementedError

    def review(self, payload: ReviewRequest) -> ReviewResult:
        raise NotImplementedError

    def rewrite_query(self, payload: QueryRewriteRequest) -> QueryRewriteResult:
        raise NotImplementedError
