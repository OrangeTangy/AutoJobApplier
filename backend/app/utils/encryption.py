from __future__ import annotations

import base64

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

_ENCRYPTED_PREFIX = "ENCRYPTED:"


def _get_fernet() -> Fernet:
    settings = get_settings()
    key = settings.database_encryption_key.encode()
    # Accept raw base64 key or URL-safe base64
    try:
        return Fernet(key)
    except Exception:
        # Try padding and re-encoding
        padded = key + b"=" * (-len(key) % 4)
        return Fernet(base64.urlsafe_b64encode(base64.urlsafe_b64decode(padded)))


def encrypt(value: str) -> str:
    """Encrypt a plaintext string. Returns ENCRYPTED:<base64_ciphertext>."""
    if not value:
        return value
    if value.startswith(_ENCRYPTED_PREFIX):
        return value  # already encrypted
    f = _get_fernet()
    ciphertext = f.encrypt(value.encode()).decode()
    return f"{_ENCRYPTED_PREFIX}{ciphertext}"


def decrypt(value: str) -> str:
    """Decrypt an ENCRYPTED:... string. Returns plaintext."""
    if not value:
        return value
    if not value.startswith(_ENCRYPTED_PREFIX):
        return value  # treat as plaintext (migration path)
    raw = value[len(_ENCRYPTED_PREFIX):].encode()
    try:
        f = _get_fernet()
        return f.decrypt(raw).decode()
    except InvalidToken as exc:
        raise ValueError("Decryption failed — key mismatch or corrupted data") from exc


def is_encrypted(value: str) -> bool:
    return value.startswith(_ENCRYPTED_PREFIX)
