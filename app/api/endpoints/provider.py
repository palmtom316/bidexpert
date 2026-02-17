from __future__ import annotations

from fastapi import APIRouter

from app.api.handlers.provider_completed_tender import (
    create_completed_bid_handler,
    create_provider_profile_handler,
    delete_completed_bid_handler,
    delete_provider_profile_handler,
    get_model_policy_handler,
    list_completed_bids_handler,
    list_provider_profiles_handler,
    put_model_policy_handler,
    qualify_provider_profile_handler,
    test_provider_profile_handler,
)
from app.schemas.contracts import (
    CompletedBidCreateRequest,
    CompletedBidDeleteResponse,
    CompletedBidItem,
    CompletedBidListResponse,
    ProjectModelPolicyResponse,
    ProjectModelPolicyUpsertRequest,
    ProviderProfileCreateRequest,
    ProviderProfileCreateResponse,
    ProviderProfileDeleteResponse,
    ProviderProfileListResponse,
    ProviderProfileQualifyResponse,
    ProviderProfileTestResponse,
)

router = APIRouter()


def _ctx():
    from app.api import routes

    return routes


@router.post("/api/provider-profiles", response_model=ProviderProfileCreateResponse)
def create_provider_profile_api(payload: ProviderProfileCreateRequest) -> ProviderProfileCreateResponse:
    ctx = _ctx()
    return create_provider_profile_handler(
        payload,
        create_provider_profile_fn=ctx.create_provider_profile,
        resolved_created_by_fn=ctx._resolved_created_by,
    )


@router.get("/api/provider-profiles", response_model=ProviderProfileListResponse)
def list_provider_profiles_api(project_id: str) -> ProviderProfileListResponse:
    ctx = _ctx()
    return list_provider_profiles_handler(
        project_id,
        list_provider_profiles_fn=ctx.list_provider_profiles,
    )


@router.post("/api/provider-profiles/{profile_id}/test", response_model=ProviderProfileTestResponse)
def test_provider_profile_api(profile_id: str) -> ProviderProfileTestResponse:
    ctx = _ctx()
    return test_provider_profile_handler(
        profile_id,
        test_provider_profile_fn=ctx.test_provider_profile,
    )


@router.post("/api/provider-profiles/{profile_id}/qualify", response_model=ProviderProfileQualifyResponse)
def qualify_provider_profile_api(
    profile_id: str,
    score_threshold: float = 80.0,
) -> ProviderProfileQualifyResponse:
    ctx = _ctx()
    return qualify_provider_profile_handler(
        profile_id,
        score_threshold,
        qualify_provider_profile_fn=ctx.qualify_provider_profile,
    )


@router.delete("/api/provider-profiles/{profile_id}", response_model=ProviderProfileDeleteResponse)
def delete_provider_profile_api(profile_id: str) -> ProviderProfileDeleteResponse:
    ctx = _ctx()
    return delete_provider_profile_handler(
        profile_id,
        delete_provider_profile_fn=ctx.delete_provider_profile,
    )


@router.put("/api/projects/{project_id}/model-policy", response_model=ProjectModelPolicyResponse)
def put_model_policy_api(project_id: str, payload: ProjectModelPolicyUpsertRequest) -> ProjectModelPolicyResponse:
    ctx = _ctx()
    return put_model_policy_handler(
        project_id,
        payload,
        upsert_project_model_policy_fn=ctx.upsert_project_model_policy,
    )


@router.get("/api/projects/{project_id}/model-policy", response_model=ProjectModelPolicyResponse)
def get_model_policy_api(project_id: str) -> ProjectModelPolicyResponse:
    ctx = _ctx()
    return get_model_policy_handler(
        project_id,
        get_project_model_policy_fn=ctx.get_project_model_policy,
    )


@router.post("/api/completed-bids", response_model=CompletedBidItem)
def create_completed_bid_api(payload: CompletedBidCreateRequest) -> CompletedBidItem:
    ctx = _ctx()
    return create_completed_bid_handler(
        payload,
        create_completed_bid_fn=ctx.create_completed_bid,
        resolved_created_by_fn=ctx._resolved_created_by,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.get("/api/completed-bids", response_model=CompletedBidListResponse)
def list_completed_bids_api(project_id: str | None = None, limit: int = 200) -> CompletedBidListResponse:
    ctx = _ctx()
    return list_completed_bids_handler(
        project_id,
        limit,
        list_completed_bids_fn=ctx.list_completed_bids,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )


@router.delete("/api/completed-bids/{record_id}", response_model=CompletedBidDeleteResponse)
def delete_completed_bid_api(record_id: str) -> CompletedBidDeleteResponse:
    ctx = _ctx()
    return delete_completed_bid_handler(
        record_id,
        delete_completed_bid_fn=ctx.delete_completed_bid,
        service_unavailable_exc_factory=ctx._service_unavailable,
    )
