"""Tests for JWT authentication utilities."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_settings_requires_jwt_secret_key() -> None:
    """Settings must reject startup if JWT_SECRET_KEY is missing."""
    with pytest.raises(ValidationError):
        Settings(
            FERNET_SECRET_KEY="dGVzdC10ZXN0LXRlc3QtdGVzdC10ZXN0LXRlc3QtdGVzdA==",
            GOOGLE_OAUTH_CLIENT_ID="client-id",
            GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
            GOOGLE_OAUTH_REDIRECT_URI="http://localhost:8000/callback",
            # JWT_SECRET_KEY intentionally omitted
            _env_file=None,
        )


from datetime import timedelta
from uuid import UUID, uuid4

import jwt

from backend.app.auth import create_access_token, decode_access_token


def test_create_and_decode_roundtrip() -> None:
    """A token created for a user_id must decode back to that user_id."""
    secret = "test-secret-key"
    user_id = uuid4()
    token = create_access_token(user_id, secret)
    assert decode_access_token(token, secret) == user_id


def test_decode_rejects_tampered_token() -> None:
    """A token signed with a different secret must raise HTTPException 401."""
    from fastapi import HTTPException

    token = create_access_token(uuid4(), "secret-a")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(token, "secret-b")
    assert exc_info.value.status_code == 401


def test_decode_rejects_expired_token() -> None:
    """An expired token must raise HTTPException 401."""
    from fastapi import HTTPException

    secret = "test-secret"
    user_id = uuid4()
    payload = {
        "sub": str(user_id),
        "exp": 0,  # epoch — already expired
    }
    expired_token = jwt.encode(payload, secret, algorithm="HS256")
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token(expired_token, secret)
    assert exc_info.value.status_code == 401


def test_decode_rejects_malformed_token() -> None:
    """A non-JWT string must raise HTTPException 401."""
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not.a.token", "secret")
    assert exc_info.value.status_code == 401
