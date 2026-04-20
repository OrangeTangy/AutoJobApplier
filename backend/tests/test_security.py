"""Tests for security utilities."""
from __future__ import annotations

import pytest

from app.utils.security import (
    compute_approval_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify():
    hashed = hash_password("mysecretpassword")
    assert hashed != "mysecretpassword"
    assert verify_password("mysecretpassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_access_token_round_trip():
    token = create_access_token("user-123")
    payload = decode_token(token)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_round_trip():
    token = create_refresh_token("user-456")
    payload = decode_token(token)
    assert payload["sub"] == "user-456"
    assert payload["type"] == "refresh"


def test_decode_invalid_token():
    with pytest.raises(ValueError):
        decode_token("not.a.valid.token")


def test_approval_hash_deterministic():
    h1 = compute_approval_hash("resume-id", ["yes", "no", "maybe"])
    h2 = compute_approval_hash("resume-id", ["yes", "no", "maybe"])
    assert h1 == h2


def test_approval_hash_order_independent():
    h1 = compute_approval_hash("resume-id", ["a", "b", "c"])
    h2 = compute_approval_hash("resume-id", ["c", "a", "b"])
    assert h1 == h2


def test_approval_hash_sensitive_to_content():
    h1 = compute_approval_hash("resume-id", ["yes"])
    h2 = compute_approval_hash("resume-id", ["no"])
    assert h1 != h2
