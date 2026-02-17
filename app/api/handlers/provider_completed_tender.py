from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, UploadFile

from app.schemas.contracts import (
    CompletedBidCreateRequest,
    CompletedBidDeleteResponse,
    CompletedBidItem,
    CompletedBidListResponse,
    ParseTenderRequest,
    ParseTenderResponse,
    ProjectModelPolicyResponse,
    ProjectModelPolicyUpsertRequest,
    ProviderProfileCreateRequest,
    ProviderProfileCreateResponse,
    ProviderProfileDeleteResponse,
    ProviderProfileItem,
    ProviderProfileListResponse,
    ProviderProfileQualifyResponse,
    ProviderProfileTestResponse,
    TenderAnalysisDetailResponse,
    TenderAnalysisRunListResponse,
    TenderAnalyzeUploadResponse,
)

DEFAULT_CONCURRENCY_LIMITS = {
    "extract": 2,
    "generate": 3,
    "review": 2,
    "embed": 2,
    "query_rewrite": 2,
    "program_support": 1,
}


def profile_to_item(profile) -> ProviderProfileItem:
    return ProviderProfileItem(
        id=str(profile.id),
        scope=str(profile.scope.value if hasattr(profile.scope, "value") else profile.scope),
        scope_id=str(profile.scope_id),
        provider=profile.provider,
        base_url=profile.base_url,
        default_model=profile.default_model,
        key_storage=str(profile.key_storage.value if hasattr(profile.key_storage, "value") else profile.key_storage),
        key_secret_ref=profile.key_secret_ref,
        allowed_tasks=profile.allowed_tasks or ["*"],
        created_by=profile.created_by,
    )


def completed_bid_to_item(record) -> CompletedBidItem:
    return CompletedBidItem(
        id=str(record.id),
        project_id=record.project_id,
        project_name=record.project_name,
        engineering_category=record.engineering_category,
        tenderer=record.tenderer,
        bid_result=record.bid_result,
        file_name=record.file_name,
        file_info=record.file_info,
        completed_date=record.completed_date.isoformat() if record.completed_date else None,
        created_by=record.created_by,
        created_at=record.created_at.isoformat() if record.created_at else "",
    )


def _policy_to_response(policy) -> ProjectModelPolicyResponse:
    return ProjectModelPolicyResponse(
        project_id=str(policy.project_id),
        extract_profile_id=str(policy.extract_profile_id) if policy.extract_profile_id else None,
        generate_profile_id=str(policy.generate_profile_id) if policy.generate_profile_id else None,
        review_profile_id=str(policy.review_profile_id) if policy.review_profile_id else None,
        embed_profile_id=str(policy.embed_profile_id) if policy.embed_profile_id else None,
        query_rewrite_profile_id=str(policy.query_rewrite_profile_id) if policy.query_rewrite_profile_id else None,
        program_support_profile_id=str(policy.program_support_profile_id) if policy.program_support_profile_id else None,
        enable_review=policy.enable_review,
        token_budget_total=int(policy.token_budget_total),
        token_budget_used=int(policy.token_budget_used),
        concurrency_limits=policy.concurrency_limits or DEFAULT_CONCURRENCY_LIMITS,
    )


def create_provider_profile_handler(
    payload: ProviderProfileCreateRequest,
    *,
    create_provider_profile_fn: Callable[..., object],
    resolved_created_by_fn: Callable[[str | None], str],
) -> ProviderProfileCreateResponse:
    try:
        profile = create_provider_profile_fn(
            project_id=payload.project_id,
            provider=payload.provider,
            base_url=payload.base_url,
            default_model=payload.default_model,
            api_key=payload.api_key,
            key_storage=payload.key_storage,
            allowed_tasks=payload.allowed_tasks,
            created_by=resolved_created_by_fn(None),
        )
        return ProviderProfileCreateResponse(
            profile_id=str(profile.id),
            key_storage=str(profile.key_storage.value),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def list_provider_profiles_handler(
    project_id: str,
    *,
    list_provider_profiles_fn: Callable[[str], list[object]],
) -> ProviderProfileListResponse:
    try:
        items = [profile_to_item(item) for item in list_provider_profiles_fn(project_id)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProviderProfileListResponse(items=items)


def test_provider_profile_handler(
    profile_id: str,
    *,
    test_provider_profile_fn: Callable[[str], tuple[object, bool, str]],
) -> ProviderProfileTestResponse:
    try:
        profile, ok, detail = test_provider_profile_fn(profile_id)
        return ProviderProfileTestResponse(
            profile_id=str(profile.id),
            ok=ok,
            provider=profile.provider,
            model=profile.default_model,
            detail=detail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def qualify_provider_profile_handler(
    profile_id: str,
    score_threshold: float,
    *,
    qualify_provider_profile_fn: Callable[..., tuple[object, dict]],
) -> ProviderProfileQualifyResponse:
    try:
        profile, result = qualify_provider_profile_fn(
            profile_id,
            score_threshold=max(0.0, min(100.0, float(score_threshold))),
        )
        return ProviderProfileQualifyResponse(
            profile_id=str(profile.id),
            provider=profile.provider,
            model=profile.default_model,
            ready_for_online=bool(result.get("ready_for_online", False)),
            threshold=float(result.get("threshold", score_threshold)),
            quality_score=float(result.get("quality_score", 0.0)),
            capability_score=float(result.get("capability_score", 0.0)),
            model_quality=result.get("model_quality", {}),
            cases=result.get("cases", []),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def delete_provider_profile_handler(
    profile_id: str,
    *,
    delete_provider_profile_fn: Callable[[str], bool],
) -> ProviderProfileDeleteResponse:
    try:
        deleted = delete_provider_profile_fn(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="provider profile not found")
    return ProviderProfileDeleteResponse(profile_id=profile_id, deleted=True)


def put_model_policy_handler(
    project_id: str,
    payload: ProjectModelPolicyUpsertRequest,
    *,
    upsert_project_model_policy_fn: Callable[..., object],
) -> ProjectModelPolicyResponse:
    try:
        policy = upsert_project_model_policy_fn(
            project_id=project_id,
            extract_profile_id=payload.extract_profile_id,
            generate_profile_id=payload.generate_profile_id,
            review_profile_id=payload.review_profile_id,
            embed_profile_id=payload.embed_profile_id,
            query_rewrite_profile_id=payload.query_rewrite_profile_id,
            program_support_profile_id=payload.program_support_profile_id,
            enable_review=payload.enable_review,
            token_budget_total=payload.token_budget_total,
            concurrency_limits=payload.concurrency_limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _policy_to_response(policy)


def get_model_policy_handler(
    project_id: str,
    *,
    get_project_model_policy_fn: Callable[[str], object],
) -> ProjectModelPolicyResponse:
    try:
        policy = get_project_model_policy_fn(project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not policy:
        raise HTTPException(status_code=404, detail="model policy not found")
    return _policy_to_response(policy)


def create_completed_bid_handler(
    payload: CompletedBidCreateRequest,
    *,
    create_completed_bid_fn: Callable[..., object],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> CompletedBidItem:
    try:
        record = create_completed_bid_fn(
            project_id=payload.project_id,
            project_name=payload.project_name,
            engineering_category=payload.engineering_category,
            tenderer=payload.tenderer,
            bid_result=payload.bid_result,
            file_name=payload.file_name,
            file_info=payload.file_info,
            completed_date=payload.completed_date,
            created_by=resolved_created_by_fn(payload.created_by),
        )
        return completed_bid_to_item(record)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def list_completed_bids_handler(
    project_id: str | None,
    limit: int,
    *,
    list_completed_bids_fn: Callable[..., list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> CompletedBidListResponse:
    try:
        records = list_completed_bids_fn(project_id=project_id, limit=limit)
        return CompletedBidListResponse(items=[completed_bid_to_item(item) for item in records])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def delete_completed_bid_handler(
    record_id: str,
    *,
    delete_completed_bid_fn: Callable[[str], bool],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> CompletedBidDeleteResponse:
    try:
        deleted = delete_completed_bid_fn(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="completed bid record not found")
    return CompletedBidDeleteResponse(record_id=record_id, deleted=True)


def parse_tender_handler(
    payload: ParseTenderRequest,
    *,
    detect_pricing_content_fn: Callable[[str], tuple[bool, list[str]]],
    parse_tender_requirements_fn: Callable[[str], object],
) -> ParseTenderResponse:
    blocked, reasons = detect_pricing_content_fn(payload.text)
    if blocked:
        raise HTTPException(status_code=400, detail={"status": "BLOCKED_PRICING_CONTENT", "reasons": reasons})

    parsed = parse_tender_requirements_fn(payload.text)
    return ParseTenderResponse(requirements=parsed.requirements, status=parsed.status)


async def analyze_tender_upload_handler(
    *,
    file: UploadFile,
    project_id: str | None,
    created_by: str,
    read_upload_with_limit_fn: Callable[[UploadFile], Awaitable[bytes]],
    analyze_and_persist_tender_pdf_fn: Callable[..., tuple[object, object]],
    resolved_created_by_fn: Callable[[str | None], str],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> TenderAnalyzeUploadResponse:
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only .pdf is supported")
    try:
        content = await read_upload_with_limit_fn(file)
        run, summary = analyze_and_persist_tender_pdf_fn(
            filename=filename,
            content=content,
            project_id=project_id,
            created_by=resolved_created_by_fn(created_by),
        )
        return TenderAnalyzeUploadResponse(
            run_id=run.run_id,
            project_id=run.project_id,
            document_id=run.document_id,
            filename=run.filename,
            status=run.status,
            summary=summary,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        raise service_unavailable_exc_factory() from exc


def list_tender_analysis_runs_handler(
    *,
    project_id: str | None,
    limit: int,
    list_tender_analysis_runs_fn: Callable[..., list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> TenderAnalysisRunListResponse:
    try:
        items = list_tender_analysis_runs_fn(project_id=project_id, limit=limit)
        return TenderAnalysisRunListResponse(items=items)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


def get_tender_analysis_detail_handler(
    *,
    run_id: str,
    get_tender_analysis_detail_fn: Callable[[str], TenderAnalysisDetailResponse],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> TenderAnalysisDetailResponse:
    try:
        return get_tender_analysis_detail_fn(run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc
