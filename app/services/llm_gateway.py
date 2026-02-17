from __future__ import annotations

import logging
from time import perf_counter
from typing import TYPE_CHECKING, Any

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
from app.services.model_quality import evaluate_compliance_quality
from app.services.routing_optimizer import build_routing_order, record_route_feedback

if TYPE_CHECKING:
    from app.services.byok.profiles import ResolvedProfile

logger = logging.getLogger(__name__)


def _select_adapter(provider: str):
    return create_adapter(provider)


def _ordered_profile_indices(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    task_type: str,
) -> list[int]:
    raw = build_routing_order(
        profile_chain=profile_chain,
        project_id=project_id,
        task_type=task_type,
    )
    seen: set[int] = set()
    order: list[int] = []
    for item in raw:
        if not isinstance(item, int):
            continue
        if item < 0 or item >= len(profile_chain):
            continue
        if item in seen:
            continue
        order.append(item)
        seen.add(item)
    for idx in range(len(profile_chain)):
        if idx not in seen:
            order.append(idx)
    return order


def _latency_ms(started_at: float) -> int:
    return max(0, int((perf_counter() - started_at) * 1000))


def _record_feedback(
    *,
    project_id: str | None,
    task_type: str,
    profile: ResolvedProfile,
    success: bool,
    latency_ms: int,
) -> None:
    try:
        record_route_feedback(
            project_id=project_id,
            task_type=task_type,
            profile=profile,
            success=success,
            latency_ms=latency_ms,
        )
    except Exception:  # noqa: BLE001
        return None


def _as_report(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _status_rank(value: str) -> int:
    normalized = str(value).strip().upper()
    if normalized == "PASS":
        return 3
    if normalized == "WARN":
        return 2
    if normalized == "FAIL":
        return 1
    return 0


def _majority_status(statuses: list[str]) -> str:
    counter: dict[str, int] = {}
    for item in statuses:
        normalized = str(item).strip().upper()
        if not normalized:
            continue
        counter[normalized] = counter.get(normalized, 0) + 1
    if not counter:
        return "FAIL"
    winner = max(counter.items(), key=lambda item: (item[1], _status_rank(item[0])))
    return winner[0]


def _merge_modeled_issues(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for report in reports:
        raw = report.get("modeled_issues", [])
        if not isinstance(raw, list):
            continue
        for issue in raw:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("requirement_code", "")).strip()
            issue_type = str(issue.get("issue_type", "")).strip().upper()
            desc = str(issue.get("description", "")).strip()
            key = (code, issue_type, desc)
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)
    return merged


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
    for idx in _ordered_profile_indices(
        profile_chain=profile_chain,
        project_id=project_id,
        task_type="GENERATE",
    ):
        profile = profile_chain[idx]
        started_at = perf_counter()
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
            _record_feedback(
                project_id=project_id,
                task_type="GENERATE",
                profile=profile,
                success=True,
                latency_ms=_latency_ms(started_at),
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
            _record_feedback(
                project_id=project_id,
                task_type="GENERATE",
                profile=profile,
                success=False,
                latency_ms=_latency_ms(started_at),
            )
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
    for idx in _ordered_profile_indices(
        profile_chain=profile_chain,
        project_id=project_id,
        task_type="REVIEW",
    ):
        profile = profile_chain[idx]
        started_at = perf_counter()
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
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=True,
                latency_ms=_latency_ms(started_at),
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
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=False,
                latency_ms=_latency_ms(started_at),
            )
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
    for idx in _ordered_profile_indices(
        profile_chain=profile_chain,
        project_id=project_id,
        task_type="REVIEW",
    ):
        profile = profile_chain[idx]
        started_at = perf_counter()
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
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=True,
                latency_ms=_latency_ms(started_at),
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
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=False,
                latency_ms=_latency_ms(started_at),
            )
            logger.warning(
                "compliance review failed for provider=%s model=%s: %s",
                profile.provider,
                profile.model,
                exc,
            )
            last_exc = exc
    raise last_exc or AdapterUnavailableError("no compliance review providers available")


def compliance_review_with_ensemble(
    *,
    profile_chain: list[ResolvedProfile],
    project_id: str | None,
    content_text: str,
    requirements: list[dict],
    ensemble_size: int = 3,
) -> tuple[ComplianceReviewResult, int]:
    """Run compliance review with multiple models and aggregate by vote + quality."""
    if not profile_chain:
        raise AdapterUnavailableError("no compliance review providers available")

    target_size = max(1, min(int(ensemble_size or 1), len(profile_chain)))
    votes: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []

    for idx in _ordered_profile_indices(
        profile_chain=profile_chain,
        project_id=project_id,
        task_type="REVIEW",
    ):
        if len(votes) >= target_size:
            break
        profile = profile_chain[idx]
        started_at = perf_counter()
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
            latency_ms = _latency_ms(started_at)
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=True,
                latency_ms=latency_ms,
            )
            report = _as_report(result.report)
            quality = evaluate_compliance_quality(status=result.status, report=report)
            votes.append(
                {
                    "index": idx,
                    "provider": profile.provider,
                    "model": profile.model,
                    "status": str(result.status).upper(),
                    "quality_score": quality,
                    "report": report,
                }
            )
        except AdapterUnavailableError as exc:
            _record_feedback(
                project_id=project_id,
                task_type="REVIEW",
                profile=profile,
                success=False,
                latency_ms=_latency_ms(started_at),
            )
            unavailable.append(
                {
                    "index": idx,
                    "provider": profile.provider,
                    "model": profile.model,
                    "error": str(exc),
                }
            )
            logger.warning(
                "ensemble compliance review failed for provider=%s model=%s: %s",
                profile.provider,
                profile.model,
                exc,
            )

    if not votes:
        raise AdapterUnavailableError("no compliance review providers available")

    final_status = _majority_status([str(item["status"]) for item in votes])
    winner = max(
        votes,
        key=lambda item: (
            float(item["quality_score"]),
            _status_rank(str(item["status"])),
            -int(item["index"]),
        ),
    )
    winner_report = dict(winner["report"])
    merged_issues = _merge_modeled_issues([item["report"] for item in votes])
    if merged_issues:
        winner_report["modeled_issues"] = merged_issues

    coverage_values: list[float] = []
    for item in votes:
        coverage = item["report"].get("coverage_estimate")
        try:
            coverage_values.append(float(coverage))
        except (TypeError, ValueError):
            continue
    if coverage_values:
        winner_report["coverage_estimate"] = round(sum(coverage_values) / len(coverage_values), 4)

    winner_report["ensemble"] = {
        "enabled": True,
        "member_count": len(votes),
        "requested_size": target_size,
        "winner_index": int(winner["index"]),
        "winner_provider": str(winner["provider"]),
        "winner_model": str(winner["model"]),
        "votes": [
            {
                "index": int(item["index"]),
                "provider": str(item["provider"]),
                "model": str(item["model"]),
                "status": str(item["status"]),
                "quality_score": round(float(item["quality_score"]), 2),
            }
            for item in votes
        ],
    }
    if unavailable:
        winner_report["ensemble"]["unavailable"] = unavailable
    winner_report["model_quality"] = {
        "score": round(float(winner["quality_score"]), 2),
        "status": str(winner["status"]),
    }

    return (
        ComplianceReviewResult(
            status=final_status,
            report=winner_report,
            provider="ensemble",
            model=f"ensemble/{len(votes)}",
        ),
        int(winner["index"]),
    )


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
    "compliance_review_with_ensemble",
    "compliance_review_with_profile",
    "rewrite_query_with_profile",
]
