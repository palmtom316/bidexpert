from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from io import BytesIO

from fastapi.testclient import TestClient

from app.main import app



def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")



def _jwt_hs256(sub: str, secret: str, exp_offset_seconds: int = 120) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset_seconds,
    }
    h = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    msg = f"{h}.{p}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), msg, hashlib.sha256).digest()
    return f"{h}.{p}.{_b64url(sig)}"



def test_health_requires_jwt_when_auth_mode_is_jwt(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes.settings, "auth_mode", "jwt", raising=False)
    monkeypatch.setattr(routes.settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", None, raising=False)

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 401



def test_health_accepts_valid_jwt(monkeypatch) -> None:
    from app.api import routes

    monkeypatch.setattr(routes.settings, "auth_mode", "jwt", raising=False)
    monkeypatch.setattr(routes.settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", None, raising=False)

    token = _jwt_hs256("alice", "test-secret")
    client = TestClient(app)
    response = client.get("/health", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"



def test_jwt_subject_overrides_created_by(monkeypatch) -> None:
    from app.api import routes

    captured: dict[str, str] = {}

    def fake_analyze_and_persist_tender_pdf(**kwargs):
        captured["created_by"] = kwargs["created_by"]
        from app.schemas.contracts import TenderAnalysisRunItem, TenderAnalysisSummary

        return (
            TenderAnalysisRunItem(
                run_id="run-1",
                project_id="proj-1",
                document_id="doc-1",
                filename="demo.pdf",
                status="SUCCEEDED",
                created_at="2026-02-17T00:00:00",
            ),
            TenderAnalysisSummary(
                total_items=0,
                category_counts={},
                key_sections=[],
                warnings=[],
            ),
        )

    monkeypatch.setattr(routes, "analyze_and_persist_tender_pdf", fake_analyze_and_persist_tender_pdf)
    monkeypatch.setattr(routes.settings, "auth_mode", "jwt", raising=False)
    monkeypatch.setattr(routes.settings, "jwt_secret", "test-secret", raising=False)
    monkeypatch.setattr(routes.settings, "api_key", None, raising=False)

    token = _jwt_hs256("owner-user", "test-secret")

    client = TestClient(app)
    response = client.post(
        "/v1/tender/analyze-upload",
        files={"file": ("demo.pdf", BytesIO(b"%PDF-1.4"), "application/pdf")},
        data={"project_id": "p-1", "created_by": "spoofed-client"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert captured["created_by"] == "owner-user"
