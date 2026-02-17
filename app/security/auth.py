from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric import utils as asymmetric_utils


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


def _normalized_algorithms(allowed_algorithms: str | Iterable[str] | None) -> set[str]:
    if allowed_algorithms is None:
        return {"HS256"}
    if isinstance(allowed_algorithms, str):
        parts = [item.strip() for item in allowed_algorithms.replace(" ", "").split(",")]
        return {item.upper() for item in parts if item}
    return {str(item).strip().upper() for item in allowed_algorithms if str(item).strip()}


def _verify_hs256_signature(*, secret: str | None, signing_input: bytes, signature: bytes) -> None:
    if not secret:
        raise ValueError("HS256 requires jwt_secret")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected_sig):
        raise ValueError("invalid jwt signature")


def _load_public_key(public_key_pem: str | None):
    if not public_key_pem:
        raise ValueError("RS256/ES256 requires jwt_public_key_pem")
    try:
        return serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except ValueError as exc:
        raise ValueError("invalid jwt_public_key_pem") from exc


def _verify_rs256_signature(*, public_key_pem: str | None, signing_input: bytes, signature: bytes) -> None:
    key = _load_public_key(public_key_pem)
    try:
        key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as exc:
        raise ValueError("invalid jwt signature") from exc
    except TypeError as exc:
        raise ValueError("invalid RSA public key for RS256") from exc


def _verify_es256_signature(*, public_key_pem: str | None, signing_input: bytes, signature: bytes) -> None:
    key = _load_public_key(public_key_pem)
    if len(signature) != 64:
        raise ValueError("invalid ES256 signature length")
    r = int.from_bytes(signature[:32], byteorder="big", signed=False)
    s = int.from_bytes(signature[32:], byteorder="big", signed=False)
    der_signature = asymmetric_utils.encode_dss_signature(r, s)
    try:
        key.verify(der_signature, signing_input, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise ValueError("invalid jwt signature") from exc
    except TypeError as exc:
        raise ValueError("invalid EC public key for ES256") from exc


def _validate_registered_claims(
    payload: dict,
    *,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
) -> None:
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


def decode_jwt(
    token: str,
    *,
    secret: str | None = None,
    public_key_pem: str | None = None,
    allowed_algorithms: str | Iterable[str] | None = None,
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

    if not isinstance(header, dict):
        raise ValueError("invalid jwt header")
    if not isinstance(payload, dict):
        raise ValueError("invalid jwt payload")

    algorithm = str(header.get("alg") or "").upper()
    allowed = _normalized_algorithms(allowed_algorithms)
    if algorithm not in allowed:
        raise ValueError(f"unsupported jwt algorithm: {algorithm or 'unknown'}")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    if algorithm == "HS256":
        _verify_hs256_signature(secret=secret, signing_input=signing_input, signature=signature)
    elif algorithm == "RS256":
        _verify_rs256_signature(
            public_key_pem=public_key_pem,
            signing_input=signing_input,
            signature=signature,
        )
    elif algorithm == "ES256":
        _verify_es256_signature(
            public_key_pem=public_key_pem,
            signing_input=signing_input,
            signature=signature,
        )
    else:
        raise ValueError(f"unsupported jwt algorithm: {algorithm}")

    _validate_registered_claims(
        payload,
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
    )
    return payload


def decode_hs256_jwt(
    token: str,
    *,
    secret: str,
    expected_issuer: str | None = None,
    expected_audience: str | None = None,
) -> dict:
    return decode_jwt(
        token,
        secret=secret,
        allowed_algorithms={"HS256"},
        expected_issuer=expected_issuer,
        expected_audience=expected_audience,
    )
