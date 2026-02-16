from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.adapters import (
    AdapterUnavailableError,
    ComplianceReviewRequest,
    ComplianceReviewResult,
    GenerationRequest,
    GenerationResult,
    QueryRewriteRequest,
    QueryRewriteResult,
    ReviewRequest,
    ReviewResult,
    create_adapter,
)
from app.services.concurrency_limiter import ConcurrencyLimitExceeded, acquire_concurrency_slot

if TYPE_CHECKING:
    from app.services.byok.profiles import ResolvedProfile

logger = logging.getLogger(__name__)


def _select_adapter(provider: str):
    return create_adapter(provider)


def generate_with_profile(
    *,
    project_id: str | None,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    requirement_text: str,
    evidence_texts: list[str],
    evidence_ids: list[str],
) -> GenerationResult:
    adapter = _select_adapter(provider)
    payload = GenerationRequest(
        model=model,
        requirement_text=requirement_text,
        evidence_texts=evidence_texts,
        evidence_ids=evidence_ids,
        api_key=api_key,
        base_url=base_url,
    )
    try:
        with acquire_concurrency_slot(project_id=project_id, task_type="GENERATE"):
            return adapter.generate(payload)
    except ConcurrencyLimitExceeded as exc:
        raise AdapterUnavailableError(str(exc)) from exc


def generate_with_fallback_chain(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    requirement_text: str,
    evidence_texts: list[str],
    evidence_ids: list[str],
) -> tuple[GenerationResult, int]:
    """Try each profile in *profile_chain* until one succeeds.

    Returns ``(result, fallback_count)`` where *fallback_count* is the
    0-based index of the profile that succeeded (0 = primary).
    Raises :class:`AdapterUnavailableError` if all profiles fail.
    """
    last_exc: AdapterUnavailableError | None = None
    for idx, profile in enumerate(profile_chain):
        try:
            result = generate_with_profile(
                project_id=project_id,
                provider=profile.provider,
                model=profile.model,
                api_key=profile.api_key,
                base_url=profile.base_url,
                requirement_text=requirement_text,
                evidence_texts=evidence_texts,
                evidence_ids=evidence_ids,
            )
            if idx > 0:
                logger.info(
                    "generate fallback succeeded at index=%d provider=%s model=%s",
                    idx,
                    profile.provider,
                    profile.model,
                )
            return result, idx
        except AdapterUnavailableError as exc:
            logger.warning(
                "generate failed for provider=%s model=%s: %s",
                profile.provider,
                profile.model,
                exc,
            )
            last_exc = exc
    raise last_exc or AdapterUnavailableError("no providers available")


def review_with_profile(
    *,
    project_id: str | None,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    draft_text: str,
    evidence_texts: list[str],
) -> ReviewResult:
    adapter = _select_adapter(provider)
    payload = ReviewRequest(
        model=model,
        draft_text=draft_text,
        evidence_texts=evidence_texts,
        api_key=api_key,
        base_url=base_url,
    )
    try:
        with acquire_concurrency_slot(project_id=project_id, task_type="REVIEW"):
            return adapter.review(payload)
    except ConcurrencyLimitExceeded as exc:
        raise AdapterUnavailableError(str(exc)) from exc


def review_with_fallback_chain(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    draft_text: str,
    evidence_texts: list[str],
) -> tuple[ReviewResult, int]:
    """Try each profile in *profile_chain* for review until one succeeds."""
    last_exc: AdapterUnavailableError | None = None
    for idx, profile in enumerate(profile_chain):
        try:
            result = review_with_profile(
                project_id=project_id,
                provider=profile.provider,
                model=profile.model,
                api_key=profile.api_key,
                base_url=profile.base_url,
                draft_text=draft_text,
                evidence_texts=evidence_texts,
            )
            if idx > 0:
                logger.info(
                    "review fallback succeeded at index=%d provider=%s model=%s",
                    idx,
                    profile.provider,
                    profile.model,
                )
            return result, idx
        except AdapterUnavailableError as exc:
            logger.warning(
                "review failed for provider=%s model=%s: %s",
                profile.provider,
                profile.model,
                exc,
            )
            last_exc = exc
    raise last_exc or AdapterUnavailableError("no review providers available")


def compliance_review_with_profile(
    *,
    project_id: str | None,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    content_text: str,
    requirements: list[dict],
) -> ComplianceReviewResult:
    adapter = _select_adapter(provider)
    payload = ComplianceReviewRequest(
        model=model,
        content_text=content_text,
        requirements=requirements,
        api_key=api_key,
        base_url=base_url,
    )
    try:
        with acquire_concurrency_slot(project_id=project_id, task_type="REVIEW"):
            return adapter.compliance_review(payload)
    except ConcurrencyLimitExceeded as exc:
        raise AdapterUnavailableError(str(exc)) from exc


def compliance_review_with_fallback_chain(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    content_text: str,
    requirements: list[dict],
) -> tuple[ComplianceReviewResult, int]:
    """Try each profile in *profile_chain* for compliance review until one succeeds."""
    last_exc: AdapterUnavailableError | None = None
    for idx, profile in enumerate(profile_chain):
        try:
            result = compliance_review_with_profile(
                project_id=project_id,
                provider=profile.provider,
                model=profile.model,
                api_key=profile.api_key,
                base_url=profile.base_url,
                content_text=content_text,
                requirements=requirements,
            )
            if idx > 0:
                logger.info(
                    "compliance review fallback succeeded at index=%d provider=%s model=%s",
                    idx,
                    profile.provider,
                    profile.model,
                )
            return result, idx
        except AdapterUnavailableError as exc:
            logger.warning(
                "compliance review failed for provider=%s model=%s: %s",
                profile.provider,
                profile.model,
                exc,
            )
            last_exc = exc
    raise last_exc or AdapterUnavailableError("no compliance review providers available")


def rewrite_query_with_profile(
    *,
    project_id: str | None,
    provider: str,
    model: str,
    api_key: str | None,
    base_url: str | None,
    query: str,
) -> QueryRewriteResult:
    adapter = _select_adapter(provider)
    payload = QueryRewriteRequest(
        model=model,
        query=query,
        api_key=api_key,
        base_url=base_url,
    )
    try:
        with acquire_concurrency_slot(project_id=project_id, task_type="QUERY_REWRITE"):
            return adapter.rewrite_query(payload)
    except ConcurrencyLimitExceeded as exc:
        raise AdapterUnavailableError(str(exc)) from exc


__all__ = [
    "AdapterUnavailableError",
    "generate_with_fallback_chain",
    "generate_with_profile",
    "review_with_fallback_chain",
    "review_with_profile",
    "compliance_review_with_fallback_chain",
    "compliance_review_with_profile",
    "rewrite_query_with_profile",
]
