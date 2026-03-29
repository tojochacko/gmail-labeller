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
