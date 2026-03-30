"""Tests for Settings startup validation."""

from __future__ import annotations

import builtins
import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from backend.app.config import Settings


_BASE = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
    "JWT_SECRET_KEY": "test-jwt-secret",
    "GOOGLE_OAUTH_CLIENT_ID": "client-id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
    "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/callback",
}


def test_startup_raises_when_openai_set_and_presidio_absent(monkeypatch) -> None:
    """Settings must raise ValidationError if OpenAI key is set but Presidio is missing."""
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name.startswith("presidio"):
            raise ImportError("presidio not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    with pytest.raises(ValidationError, match="presidio"):
        Settings.model_validate({**_BASE, "OPENAI_API_KEY": "sk-test-key"})


def test_startup_succeeds_when_openai_absent() -> None:
    """Settings must not raise when no cloud LLM key is configured."""
    Settings.model_validate(_BASE)  # no OPENAI_API_KEY — must not raise


def test_startup_succeeds_when_presidio_present_and_openai_set(monkeypatch) -> None:
    """Settings must not raise when both OpenAI key and Presidio are available."""
    try:
        import presidio_analyzer  # noqa: F401
    except ImportError:
        pytest.skip("presidio-analyzer not installed")

    Settings.model_validate({**_BASE, "OPENAI_API_KEY": "sk-test-key"})
