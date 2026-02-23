from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, UploadFile

from app.schemas.contracts import (
    OCRConnectionTestRequest,
    OCRConnectionTestResponse,
    AuditLogItem,
    AuditLogListResponse,
    CompletedBidCreateRequest,
    CompletedBidDeleteResponse,
    CompletedBidItem,
    CompletedBidListResponse,
    ParseTenderRequest,
    ParseTenderResponse,
    ProjectModelPolicyResponse,
    ProjectModelPolicyUpsertRequest,
    ProviderConnectionTestRequest,
    ProviderConnectionTestResponse,
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
    "rerank": 2,
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
        project_id=str(record.project_id) if record.project_id else None,
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


def audit_log_to_item(row) -> AuditLogItem:
    created_at = getattr(row, "created_at", None)
    return AuditLogItem(
        id=str(row.id),
        project_id=str(row.project_id) if getattr(row, "project_id", None) else None,
        actor_user_id=str(row.actor_user_id),
        action=str(row.action),
        target_id=str(row.target_id) if getattr(row, "target_id", None) else None,
        metadata=getattr(row, "metadata_json", {}) or {},
        created_at=created_at.isoformat() if created_at else "",
    )


def _policy_changed_fields(payload: ProjectModelPolicyUpsertRequest) -> list[str]:
    fields: list[str] = []
    for field_name in (
        "extract_profile_id",
        "generate_profile_id",
        "review_profile_id",
        "embed_profile_id",
        "rerank_profile_id",
        "query_rewrite_profile_id",
        "program_support_profile_id",
    ):
        if getattr(payload, field_name) is not None:
            fields.append(field_name)
    if payload.token_budget_total is not None:
        fields.append("token_budget_total")
    if payload.concurrency_limits is not None:
        fields.append("concurrency_limits")
    fields.append("enable_review")
    return fields


def _policy_to_response(policy) -> ProjectModelPolicyResponse:
    return ProjectModelPolicyResponse(
        project_id=str(policy.project_id),
        extract_profile_id=str(policy.extract_profile_id) if policy.extract_profile_id else None,
        generate_profile_id=str(policy.generate_profile_id) if policy.generate_profile_id else None,
        review_profile_id=str(policy.review_profile_id) if policy.review_profile_id else None,
        embed_profile_id=str(policy.embed_profile_id) if policy.embed_profile_id else None,
        rerank_profile_id=str(policy.rerank_profile_id) if policy.rerank_profile_id else None,
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
    audit_log_fn: Callable[..., None] | None = None,
) -> ProviderProfileCreateResponse:
    try:
        actor_user_id = resolved_created_by_fn(None)
        profile = create_provider_profile_fn(
            project_id=payload.project_id,
            provider=payload.provider,
            base_url=payload.base_url,
            default_model=payload.default_model,
            api_key=payload.api_key,
            key_storage=payload.key_storage,
            allowed_tasks=payload.allowed_tasks,
            created_by=actor_user_id,
        )
        if audit_log_fn:
            audit_log_fn(
                action="provider_profile.create",
                actor_user_id=actor_user_id,
                project_id=payload.project_id,
                target_id=str(profile.id),
                metadata={
                    "provider": payload.provider,
                    "default_model": payload.default_model,
                    "key_storage": payload.key_storage,
                    "allowed_tasks": payload.allowed_tasks,
                },
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


def test_provider_connection_handler(
    payload: ProviderConnectionTestRequest,
    *,
    test_provider_connection_fn: Callable[..., tuple[bool, str]],
) -> ProviderConnectionTestResponse:
    try:
        ok, detail = test_provider_connection_fn(
            provider=payload.provider,
            default_model=payload.default_model,
            api_key=payload.api_key,
            base_url=payload.base_url,
        )
        return ProviderConnectionTestResponse(
            ok=ok,
            provider=payload.provider,
            model=payload.default_model,
            detail=detail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def test_ocr_connection_handler(
    payload: OCRConnectionTestRequest,
    *,
    test_ocr_connection_fn: Callable[..., tuple[str, str, bool, str]],
) -> OCRConnectionTestResponse:
    try:
        provider, model, ok, detail = test_ocr_connection_fn(
            provider=payload.provider,
            api_key=payload.api_key,
            base_url=payload.base_url,
            model=payload.model,
        )
        return OCRConnectionTestResponse(
            ok=ok,
            provider=provider,
            model=model,
            detail=detail,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
    resolved_created_by_fn: Callable[[str | None], str],
    audit_log_fn: Callable[..., None] | None = None,
) -> ProviderProfileDeleteResponse:
    try:
        deleted = delete_provider_profile_fn(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="provider profile not found")
    if audit_log_fn:
        audit_log_fn(
            action="provider_profile.delete",
            actor_user_id=resolved_created_by_fn(None),
            project_id=None,
            target_id=profile_id,
            metadata={},
        )
    return ProviderProfileDeleteResponse(profile_id=profile_id, deleted=True)


def put_model_policy_handler(
    project_id: str,
    payload: ProjectModelPolicyUpsertRequest,
    *,
    upsert_project_model_policy_fn: Callable[..., object],
    resolved_created_by_fn: Callable[[str | None], str],
    audit_log_fn: Callable[..., None] | None = None,
) -> ProjectModelPolicyResponse:
    try:
        policy = upsert_project_model_policy_fn(
            project_id=project_id,
            extract_profile_id=payload.extract_profile_id,
            generate_profile_id=payload.generate_profile_id,
            review_profile_id=payload.review_profile_id,
            embed_profile_id=payload.embed_profile_id,
            rerank_profile_id=payload.rerank_profile_id,
            query_rewrite_profile_id=payload.query_rewrite_profile_id,
            program_support_profile_id=payload.program_support_profile_id,
            enable_review=payload.enable_review,
            token_budget_total=payload.token_budget_total,
            concurrency_limits=payload.concurrency_limits,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if audit_log_fn:
        audit_log_fn(
            action="model_policy.upsert",
            actor_user_id=resolved_created_by_fn(None),
            project_id=project_id,
            target_id=project_id,
            metadata={
                "changed_fields": _policy_changed_fields(payload),
                "enable_review": payload.enable_review,
            },
        )
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
    audit_log_fn: Callable[..., None] | None = None,
) -> CompletedBidItem:
    try:
        actor_user_id = resolved_created_by_fn(payload.created_by)
        record = create_completed_bid_fn(
            project_id=payload.project_id,
            project_name=payload.project_name,
            engineering_category=payload.engineering_category,
            tenderer=payload.tenderer,
            bid_result=payload.bid_result,
            file_name=payload.file_name,
            file_info=payload.file_info,
            completed_date=payload.completed_date,
            created_by=actor_user_id,
        )
        if audit_log_fn:
            audit_log_fn(
                action="completed_bid.create",
                actor_user_id=actor_user_id,
                project_id=payload.project_id,
                target_id=str(record.id),
                metadata={
                    "project_name": payload.project_name,
                    "bid_result": payload.bid_result,
                    "file_name": payload.file_name,
                },
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
    resolved_created_by_fn: Callable[[str | None], str],
    audit_log_fn: Callable[..., None] | None = None,
) -> CompletedBidDeleteResponse:
    try:
        deleted = delete_completed_bid_fn(record_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="completed bid record not found")
    if audit_log_fn:
        audit_log_fn(
            action="completed_bid.delete",
            actor_user_id=resolved_created_by_fn(None),
            project_id=None,
            target_id=record_id,
            metadata={},
        )
    return CompletedBidDeleteResponse(record_id=record_id, deleted=True)


def list_audit_logs_handler(
    *,
    project_id: str | None,
    action: str | None,
    limit: int,
    list_audit_logs_fn: Callable[..., list[object]],
    service_unavailable_exc_factory: Callable[[], HTTPException],
) -> AuditLogListResponse:
    try:
        rows = list_audit_logs_fn(project_id=project_id, action=action, limit=limit)
        return AuditLogListResponse(items=[audit_log_to_item(row) for row in rows])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise service_unavailable_exc_factory() from exc


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
