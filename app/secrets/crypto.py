from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_SIZE = 12


def load_master_key() -> bytes:
    raw = settings.master_key_b64 or os.getenv("MASTER_KEY_B64")
    if not raw:
        raise ValueError("MASTER_KEY_B64 is required for encrypted key storage")
    try:
        key = base64.b64decode(raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("MASTER_KEY_B64 is not valid base64") from exc
    if len(key) != 32:
        raise ValueError("MASTER_KEY_B64 must decode to 32 bytes")
    return key


def encrypt(api_key: str, master_key: bytes) -> bytes:
    nonce = os.urandom(_NONCE_SIZE)
    ciphertext_with_tag = AESGCM(master_key).encrypt(nonce, api_key.encode("utf-8"), None)
    return nonce + ciphertext_with_tag


def decrypt(blob: bytes, master_key: bytes) -> str:
    if len(blob) <= _NONCE_SIZE:
        raise ValueError("encrypted key payload is invalid")
    nonce = blob[:_NONCE_SIZE]
    ciphertext_with_tag = blob[_NONCE_SIZE:]
    plaintext = AESGCM(master_key).decrypt(nonce, ciphertext_with_tag, None)
    return plaintext.decode("utf-8")
