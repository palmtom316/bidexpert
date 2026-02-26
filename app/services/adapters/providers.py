from __future__ import annotations

import json
import re
from functools import lru_cache

import httpx

from app.core.config import settings
from app.llm.prompt_suite_v11 import (
    CLAUDE_PROMPT_TEMPERATURE,
    build_review_prompt,
    build_section_generation_prompt,
)
from app.services.adapters.base import (
    AdapterUnavailableError,
    ComplianceReviewRequest,
    ComplianceReviewResult,
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
    ensure_generation_evidence_binding,
    flatten_generation_payload,
    validate_compliance_payload,
    validate_generation_payload,
    validate_review_payload,
)


def _local_compose(requirement_text: str, evidence_texts: list[str]) -> str:
    snippets = [text.strip().split("。", maxsplit=1)[0] for text in evidence_texts if text.strip()]
    if not snippets:
        return ""
    return f"针对要求“{requirement_text}”，我们具备以下能力：" + "；".join(snippets[:3]) + "。"


@lru_cache(maxsize=4)
def _shared_http_client(timeout_seconds: float) -> httpx.Client:
    timeout = httpx.Timeout(timeout_seconds)
    return httpx.Client(timeout=timeout)


def _should_retry_without_response_format(exc: httpx.HTTPStatusError, response_format: dict | None) -> bool:
    if not isinstance(response_format, dict):
        return False
    if exc.response.status_code not in {400, 404, 415, 422}:
        return False
    text = (exc.response.text or "").lower()
    return "response_format" in text or "json_object" in text


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

    def compliance_review(self, payload: ComplianceReviewRequest) -> ComplianceReviewResult:
        issues = []
        if "fail" in payload.content_text.lower():
            issues.append("mock_forced_fail")
        
        status = "FAIL" if issues else "PASS"
        report = {
            "status": status,
            "modeled_issues": [{"requirement_code": "req1", "description": i} for i in issues],
            "general_comments": "Mock review completed."
        }
        return ComplianceReviewResult(
            status=status,
            report=report,
            provider=self.provider,
            model=payload.model,
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

    def _post_chat(
        self,
        *,
        model: str,
        prompt: str,
        api_key: str | None,
        base_url: str | None,
        temperature: float = 0.2,
        response_format: dict | None = None,
    ) -> str:
        if not api_key or not base_url:
            raise AdapterUnavailableError("missing api_key or base_url")

        url = f"{base_url.rstrip('/')}/chat/completions"
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }
        if isinstance(response_format, dict):
            body["response_format"] = response_format
        def _send(request_body: dict) -> dict:
            resp = client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                json=request_body,
            )
            resp.raise_for_status()
            return resp.json()
        try:
            client = _shared_http_client(float(settings.llm_http_timeout_seconds))
            raw = _send(body)
        except httpx.TimeoutException as exc:
            raise AdapterUnavailableError("provider timeout") from exc
        except httpx.HTTPStatusError as exc:
            if _should_retry_without_response_format(exc, response_format):
                fallback_body = dict(body)
                fallback_body.pop("response_format", None)
                try:
                    raw = _send(fallback_body)
                except httpx.TimeoutException as retry_exc:
                    raise AdapterUnavailableError("provider timeout") from retry_exc
                except httpx.HTTPStatusError as retry_exc:
                    raise AdapterUnavailableError(f"provider returned {retry_exc.response.status_code}") from retry_exc
                except (httpx.HTTPError, json.JSONDecodeError) as retry_exc:
                    raise AdapterUnavailableError("provider unavailable") from retry_exc
            else:
                raise AdapterUnavailableError(f"provider returned {exc.response.status_code}") from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
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
        evidence_ids = payload.evidence_ids or ["NEED_EVIDENCE"]
        top_chunks = payload.top_chunks
        if not top_chunks:
            top_chunks = []
            for idx, text in enumerate(payload.evidence_texts[:20], start=1):
                eid = payload.evidence_ids[idx - 1] if idx - 1 < len(payload.evidence_ids) else f"e-{idx}"
                top_chunks.append(
                    {
                        "chunk_id": eid,
                        "text": text,
                        "parent_context": text,
                    }
                )
        prompt = build_section_generation_prompt(
            global_facts_json=payload.global_facts or {},
            relevant_requirements=payload.relevant_requirements or [payload.requirement_text],
            relevant_scoring=payload.relevant_scoring or [],
            top_chunks=top_chunks,
        )
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
            temperature=float(CLAUDE_PROMPT_TEMPERATURE["section_generate"]),
        )
        try:
            structured = ensure_generation_evidence_binding(
                validate_generation_payload(content),
                allowed_evidence_ids=payload.evidence_ids,
            )
        except ValueError:
            structured = build_generation_payload(content, evidence_ids)
        return GenerationResult(
            text=flatten_generation_payload(structured),
            provider=self.provider,
            model=payload.model,
            content_json=structured.model_dump(mode="json"),
        )

    def review(self, payload: ReviewRequest) -> ReviewResult:
        prompt = build_review_prompt({"draft_text": payload.draft_text, "evidence": payload.evidence_texts[:20]})
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
            temperature=float(CLAUDE_PROMPT_TEMPERATURE["review"]),
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

    def compliance_review(self, payload: ComplianceReviewRequest) -> ComplianceReviewResult:
        req_lines = []
        for r in payload.requirements:
            code = r.get("requirement_code", "?")
            strength = r.get("strength", "MUST")
            text = r.get("original_text", "")
            req_lines.append(f"- [{code}] ({strength}) {text}")
        
        req_text = "\n".join(req_lines)
        prompt = (
            "你是合规审查员。请严格对照要求审查内容。\n"
            "要求列表：\n"
            f"{req_text}\n\n"
            f"待审查内容：\n{payload.content_text}\n\n"
            "必须输出 JSON：\n"
            '{"status": "PASS"|"FAIL"|"WARN", "modeled_issues": [{"requirement_code": "...", "issue_type": "NON_COMPLIANT"|"MISSING", "description": "...", "location_snippet": "..."}], "general_comments": "..."}'
        )
        content = self._post_chat(
            model=payload.model,
            prompt=prompt,
            api_key=payload.api_key,
            base_url=payload.base_url,
            response_format={"type": "json_object"},
        )
        try:
            parsed = validate_compliance_payload(content)
            return ComplianceReviewResult(
                status=parsed.status,
                report=parsed.model_dump(mode="json"),
                provider=self.provider,
                model=payload.model,
            )
        except ValueError:
            fallback = {
                "status": "FAIL",
                "modeled_issues": [{"requirement_code": "PARSE_ERROR", "description": "LLM output parsing failed"}],
                "general_comments": "Failed to parse LLM response"
            }
            return ComplianceReviewResult(
                status="FAIL",
                report=fallback,
                provider=self.provider,
                model=payload.model,
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
            response_format={"type": "json_object"},
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


class VoyageAdapter(LLMAdapter):
    provider = "voyage"

    def generate(self, payload: GenerationRequest) -> GenerationResult:
        raise AdapterUnavailableError("voyage provider only supports embedding tasks")

    def review(self, payload: ReviewRequest) -> ReviewResult:
        raise AdapterUnavailableError("voyage provider only supports embedding tasks")

    def compliance_review(self, payload: ComplianceReviewRequest) -> ComplianceReviewResult:
        raise AdapterUnavailableError("voyage provider only supports embedding tasks")

    def rewrite_query(self, payload: QueryRewriteRequest) -> QueryRewriteResult:
        raise AdapterUnavailableError("voyage provider only supports embedding tasks")
