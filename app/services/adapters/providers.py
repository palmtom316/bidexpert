from __future__ import annotations

import json
from urllib import error, request

from app.services.adapters.base import (
    AdapterUnavailableError,
    GenerationRequest,
    GenerationResult,
    LLMAdapter,
    ReviewRequest,
    ReviewResult,
)


def _local_compose(requirement_text: str, evidence_texts: list[str]) -> str:
    snippets = [text.strip().split("。", maxsplit=1)[0] for text in evidence_texts if text.strip()]
    if not snippets:
        return ""
    return f"针对要求“{requirement_text}”，我们具备以下能力：" + "；".join(snippets[:3]) + "。"


class MockAdapter(LLMAdapter):
    provider = "mock"

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        return GenerationResult(
            text=_local_compose(payload.requirement_text, payload.evidence_texts),
            provider=self.provider,
            model=payload.model,
        )

    def review(self, payload: ReviewRequest) -> ReviewResult:
        issues: list[str] = []
        draft = payload.draft_text.strip()
        if not draft:
            issues.append("empty_draft")
        if len(draft) < 20:
            issues.append("draft_too_short")
        approved = not issues
        return ReviewResult(approved=approved, issues=issues, provider=self.provider, model=payload.model)


class OpenAICompatibleAdapter(LLMAdapter):
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def _post_chat(self, *, model: str, prompt: str, api_key: str | None, base_url: str | None) -> str:
        if not api_key or not base_url:
            raise AdapterUnavailableError("missing api_key or base_url")

        url = f"{base_url.rstrip('/')}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
        }
        req = request.Request(
            url,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            data=json.dumps(body).encode("utf-8"),
        )
        try:
            with request.urlopen(req, timeout=12) as resp:  # noqa: S310
                raw = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            raise AdapterUnavailableError(f"provider unavailable: {exc.reason}") from exc
        except (TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AdapterUnavailableError("provider unavailable") from exc

        choices = raw.get("choices") if isinstance(raw, dict) else None
        if not choices:
            raise AdapterUnavailableError("provider returned no choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise AdapterUnavailableError("provider returned invalid content")
        return content

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        evidence = "\n".join(payload.evidence_texts[:6])
        prompt = (
            "你是投标写作助手。仅基于证据写作。\n"
            f"要求：{payload.requirement_text}\n"
            f"证据：\n{evidence}\n"
            "输出一段简洁文本。"
        )
        text = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        return GenerationResult(text=text, provider=self.provider, model=payload.model)

    def review(self, payload: ReviewRequest) -> ReviewResult:
        evidence = "\n".join(payload.evidence_texts[:6])
        prompt = (
            "你是审查员。判断草稿是否由证据支撑，并给出JSON："
            '{"approved": bool, "issues": string[]}\n'
            f"草稿：{payload.draft_text}\n"
            f"证据：\n{evidence}"
        )
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        try:
            parsed = json.loads(content)
            approved = bool(parsed.get("approved"))
            issues = parsed.get("issues")
            if not isinstance(issues, list):
                issues = []
            issues = [str(item) for item in issues]
            return ReviewResult(approved=approved, issues=issues, provider=self.provider, model=payload.model)
        except json.JSONDecodeError:
            return ReviewResult(approved=False, issues=["review_parse_failed"], provider=self.provider, model=payload.model)
