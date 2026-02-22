from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api import routes


def test_qualify_provider_profile_api_route(monkeypatch) -> None:
    profile = SimpleNamespace(
        id=uuid4(),
        provider="openai",
        default_model="gpt-5",
    )
    payload = {
        "ready_for_online": True,
        "threshold": 80.0,
        "quality_score": 92.5,
        "capability_score": 95.0,
        "model_quality": {"score": 90.0},
        "cases": [
            {
                "case_id": "credential_resolved",
                "name": "Credential Resolved",
                "weight": 20.0,
                "passed": True,
                "detail": "credential resolved",
            }
        ],
    }
    monkeypatch.setattr(routes, "qualify_provider_profile", lambda *_args, **_kwargs: (profile, payload))

    resp = routes.qualify_provider_profile_api(str(profile.id), score_threshold=88.0)

    assert resp.profile_id == str(profile.id)
    assert resp.provider == "openai"
    assert resp.model == "gpt-5"
    assert resp.ready_for_online is True
    assert resp.quality_score == 92.5
    assert resp.cases[0].case_id == "credential_resolved"


def test_qualify_provider_profile_api_route_returns_not_found_on_unsupported_provider(monkeypatch) -> None:
    monkeypatch.setattr(
        routes,
        "qualify_provider_profile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("unsupported provider: x")),
    )

    with pytest.raises(HTTPException) as exc_info:
        routes.qualify_provider_profile_api(str(uuid4()), score_threshold=80.0)

    assert exc_info.value.status_code == 404
    assert "unsupported provider" in str(exc_info.value.detail)
