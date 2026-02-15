from __future__ import annotations

import json
import re
from urllib import error, request

from app.services.adapters.base import (
    AdapterUnavailableError,
    GenerationRequest,
    GenerationResult,
    LLMAdapter,
    QueryRewriteRequest,
    QueryRewriteResult,
    ReviewRequest,
    ReviewResult,
)
from app.validator import (
    build_generation_payload,
    flatten_generation_payload,
    validate_generation_payload,
    validate_review_payload,
)


def _local_compose(requirement_text: str, evidence_texts: list[str]) -> str:
    snippets = [text.strip().split("。", maxsplit=1)[0] for text in evidence_texts if text.strip()]
    if not snippets:
        return ""
    return f"针对要求“{requirement_text}”，我们具备以下能力：" + "；".join(snippets[:3]) + "。"


class MockAdapter(LLMAdapter):
    provider = "mock"

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        evidence_ids = payload.evidence_ids or ["NEED_EVIDENCE"]
        structured = build_generation_payload(
            _local_compose(payload.requirement_text, payload.evidence_texts) or "NEED_HUMAN_INPUT",
            evidence_ids,
        )
        return GenerationResult(
            text=flatten_generation_payload(structured),
            provider=self.provider,
            model=payload.model,
            content_json=structured.model_dump(mode="json"),
        )

    def review(self, payload: ReviewRequest) -> ReviewResult:
        issues: list[str] = []
        draft = payload.draft_text.strip()
        if not draft:
            issues.append("empty_draft")
        if len(draft) < 20:
            issues.append("draft_too_short")
        approved = not issues
        report = {
            "missing_requirements": [],
            "logical_inconsistencies": [],
            "risk_points": issues.copy(),
            "coverage_estimate": 1.0 if approved else 0.0,
            "score_estimate": 85.0 if approved else 30.0,
            "approved": approved,
            "issues": issues,
        }
        return ReviewResult(
            approved=approved,
            issues=issues,
            provider=self.provider,
            model=payload.model,
            report=report,
        )

    def rewrite_query(self, payload: QueryRewriteRequest) -> QueryRewriteResult:
        rewritten = re.sub(r"\s+", " ", payload.query).strip()
        return QueryRewriteResult(
            rewritten_query=rewritten,
            provider=self.provider,
            model=payload.model,
        )


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
        evidence_rows = []
        evidence_ids = payload.evidence_ids or ["NEED_EVIDENCE"]
        for idx, text in enumerate(payload.evidence_texts[:6], start=1):
            eid = payload.evidence_ids[idx - 1] if idx - 1 < len(payload.evidence_ids) else f"e-{idx}"
            evidence_rows.append(f"- evidence_id={eid}: {text}")
        evidence = "\n".join(evidence_rows)
        prompt = (
            "你是投标写作助手。仅基于证据写作。\n"
            "必须输出JSON对象："
            '{"content_blocks":[{"type":"paragraph","text":"...","evidence_ids":["e-1"]}]}\n'
            "若证据不足，text 输出 NEED_HUMAN_INPUT。\n"
            f"要求：{payload.requirement_text}\n"
            f"证据：\n{evidence}\n"
            "不要输出 JSON 以外内容。"
        )
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        try:
            structured = validate_generation_payload(content)
        except ValueError:
            structured = build_generation_payload(content, evidence_ids)
        return GenerationResult(
            text=flatten_generation_payload(structured),
            provider=self.provider,
            model=payload.model,
            content_json=structured.model_dump(mode="json"),
        )

    def review(self, payload: ReviewRequest) -> ReviewResult:
        evidence = "\n".join(payload.evidence_texts[:6])
        prompt = (
            "你是审查员。仅输出JSON对象："
            '{"missing_requirements":[],"logical_inconsistencies":[],"risk_points":[],"coverage_estimate":0.0,"score_estimate":0.0,"approved":true,"issues":[]}\n'
            "不得改写正文，只输出分析。\n"
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
            parsed = validate_review_payload(content)
            issues = [str(item) for item in (parsed.issues or [])]
            issues.extend([f"missing_requirement:{item}" for item in parsed.missing_requirements])
            issues.extend([f"logical_inconsistency:{item}" for item in parsed.logical_inconsistencies])
            issues.extend([f"risk_point:{item}" for item in parsed.risk_points])
            approved = bool(parsed.approved) and not issues
            return ReviewResult(
                approved=approved,
                issues=issues,
                provider=self.provider,
                model=payload.model,
                report=parsed.model_dump(mode="json"),
            )
        except ValueError:
            fallback = {
                "missing_requirements": [],
                "logical_inconsistencies": [],
                "risk_points": ["review_parse_failed"],
                "coverage_estimate": 0.0,
                "score_estimate": 0.0,
                "approved": False,
                "issues": ["review_parse_failed"],
            }
            return ReviewResult(
                approved=False,
                issues=["review_parse_failed"],
                provider=self.provider,
                model=payload.model,
                report=fallback,
            )

    def rewrite_query(self, payload: QueryRewriteRequest) -> QueryRewriteResult:
        prompt = (
            "你是检索查询重写器。请把输入改写为更适合知识库检索的一句话。\n"
            '仅输出 JSON：{"rewritten_query":"..."}\n'
            f"输入：{payload.query}"
        )
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        rewritten = payload.query
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict) and isinstance(parsed.get("rewritten_query"), str):
                rewritten = parsed["rewritten_query"].strip() or payload.query
            elif isinstance(parsed, str):
                rewritten = parsed.strip() or payload.query
        except json.JSONDecodeError:
            rewritten = content.strip() or payload.query
        return QueryRewriteResult(
            rewritten_query=rewritten,
            provider=self.provider,
            model=payload.model,
        )


class OpenAIAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(provider="openai")


class GeminiAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(provider="gemini")


class QwenAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(provider="qwen")


class DeepSeekAdapter(OpenAICompatibleAdapter):
    def __init__(self) -> None:
        super().__init__(provider="deepseek")
