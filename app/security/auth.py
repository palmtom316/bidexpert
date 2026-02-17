from __future__ import annotations

import base64
import hashlib
import hmac
import json
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    method: str  # jwt | api_key | anonymous


_AUTH_CONTEXT: ContextVar[AuthContext] = ContextVar(
    "auth_context",
    default=AuthContext(user_id="system", method="anonymous"),
)


def set_auth_context(context: AuthContext) -> None:
    _AUTH_CONTEXT.set(context)


def get_auth_context() -> AuthContext:
    return _AUTH_CONTEXT.get()


def _b64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def decode_hs256_jwt(
    token: str,
    *,
    secret: str,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid jwt format")

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        signature = _b64url_decode(signature_b64)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("invalid jwt encoding") from exc

    if not isinstance(header, dict) or header.get("alg") != "HS256":
        raise ValueError("unsupported jwt algorithm")
    if not isinstance(payload, dict):
        raise ValueError("invalid jwt payload")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("invalid jwt signature")

    now = int(datetime.now(UTC).timestamp())

    exp = payload.get("exp")
    if exp is not None:
        try:
            if int(exp) < now:
                raise ValueError("jwt expired")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid jwt exp") from exc

    nbf = payload.get("nbf")
    if nbf is not None:
        try:
            if int(nbf) > now:
                raise ValueError("jwt not active yet")
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid jwt nbf") from exc

    if expected_issuer:
        if str(payload.get("iss", "")) != expected_issuer:
            raise ValueError("invalid jwt issuer")

    if expected_audience:
        aud = payload.get("aud")
        if isinstance(aud, list):
            if expected_audience not in [str(item) for item in aud]:
                raise ValueError("invalid jwt audience")
        elif str(aud or "") != expected_audience:
            raise ValueError("invalid jwt audience")

    return payload
