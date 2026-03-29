"""Route-level tests for the FastAPI backend."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


def test_healthcheck(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_oauth_start_returns_authorization_url(client: TestClient) -> None:
    payload = {"user_id": str(uuid4()), "email": "user@example.com"}
    response = client.post("/api/oauth/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "authorization_url" in data and data["authorization_url"].startswith(
        "https://example.com"
    )
    assert "state" in data and len(data["state"]) > 0


def test_oauth_callback_stores_tokens_and_returns_token(
    client: TestClient, fake_supabase
) -> None:
    user_id = uuid4()
    state = f"{user_id}.somesecret"
    response = client.get(f"/api/oauth/callback?code=auth-code&state={state}")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert "access_token" in data
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    assert user_id in fake_supabase.tokens


def test_list_emails_requires_auth(client: TestClient) -> None:
    """GET /api/emails without a token must return 401."""
    response = client.get("/api/emails")
    assert response.status_code == 401


def test_list_emails_with_auth(authed_client: TestClient) -> None:
    """GET /api/emails with a valid token must return email items."""
    response = authed_client.get("/api/emails")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data and len(data["items"]) == 1


def test_apply_label_requires_auth(client: TestClient) -> None:
    """POST /api/labels without a token must return 401."""
    payload = {
        "user_id": str(uuid4()),
        "gmail_message_id": "msg-1",
        "label_name": "AUTO_LABEL",
    }
    response = client.post("/api/labels", json=payload)
    assert response.status_code == 401


def test_apply_label_with_auth(authed_client: TestClient) -> None:
    """POST /api/labels with a valid token must succeed."""
    payload = {
        "gmail_message_id": "msg-1",
        "label_name": "AUTO_LABEL",
    }
    response = authed_client.post("/api/labels", json=payload)
    assert response.status_code == 200
    assert response.json()["label"] == "AUTO_LABEL"


def test_create_session_requires_auth(client: TestClient) -> None:
    """POST /api/sessions without a token must return 401."""
    response = client.post("/api/sessions", json={"max_results": 5})
    assert response.status_code == 401


def test_get_session_requires_auth(client: TestClient) -> None:
    """GET /api/sessions/{id} without a token must return 401."""
    response = client.get(f"/api/sessions/{uuid4()}")
    assert response.status_code == 401


def test_run_session_requires_auth(client: TestClient) -> None:
    """POST /api/sessions/{id}/run without a token must return 401."""
    response = client.post(f"/api/sessions/{uuid4()}/run")
    assert response.status_code == 401


def test_cleanup_session_requires_auth(client: TestClient) -> None:
    """POST /api/sessions/{id}/cleanup without a token must return 401."""
    response = client.post(f"/api/sessions/{uuid4()}/cleanup")
    assert response.status_code == 401


def test_get_session_emails_requires_auth(client: TestClient) -> None:
    """GET /api/sessions/{id}/emails without a token must return 401."""
    response = client.get(f"/api/sessions/{uuid4()}/emails")
    assert response.status_code == 401


def test_list_patterns_requires_auth(client: TestClient) -> None:
    """GET /api/patterns without a token must return 401."""
    response = client.get("/api/patterns")
    assert response.status_code == 401


def test_extract_patterns_requires_auth(client: TestClient) -> None:
    """POST /api/patterns/extract without a token must return 401."""
    response = client.post("/api/patterns/extract", json={
        "subject": "Test", "sender_email": "a@b.com", "label_type": "Important"
    })
    assert response.status_code == 401


def test_review_page_requires_auth(client: TestClient) -> None:
    """GET /api/review/{id} without a token must return 401."""
    response = client.get(f"/api/review/{uuid4()}")
    assert response.status_code == 401


def test_correct_label_requires_auth(client: TestClient) -> None:
    """POST /api/review/{id}/correct without a token must return 401."""
    payload = {
        "email_id": str(uuid4()),
        "gmail_message_id": "msg-1",
        "new_label": "Important",
    }
    response = client.post(f"/api/review/{uuid4()}/correct", json=payload)
    assert response.status_code == 401


def test_agent_run_endpoints(client: TestClient, fake_agent_service) -> None:
    payload = {
        "user_id": str(uuid4()),
        "email_id": str(uuid4()),
        "gmail_message_id": "msg-1",
    }
    trigger_response = client.post("/api/runs", json=payload)
    assert trigger_response.status_code == 202
    run_id = trigger_response.json()["run_id"]

    status_response = client.get(f"/api/runs/{run_id}")
    assert status_response.status_code == 200
    status_data = status_response.json()
    assert status_data["status"] == "completed"
    assert status_data["result_payload"]["summary"] == "done"


def test_debug_endpoints_disabled_in_non_dev(client: TestClient) -> None:
    """Debug endpoints must return 403 when environment is not 'development'."""
    response = client.get(f"/api/debug/emails/{uuid4()}")
    assert response.status_code == 403


def test_require_dev_guard_raises_403_in_production() -> None:
    """_require_dev dependency raises 403 when environment is 'production'."""
    from cryptography.fernet import Fernet

    from backend.app.config import Settings
    from backend.app.routes.debug import _require_dev

    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": "test-secret",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/callback",
            "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
            "ENVIRONMENT": "production",
        }
    )
    with pytest.raises(HTTPException) as exc_info:
        _require_dev(settings=settings)
    assert exc_info.value.status_code == 403


def test_require_dev_guard_passes_in_development() -> None:
    """_require_dev dependency does not raise when environment is 'development'."""
    from cryptography.fernet import Fernet

    from backend.app.config import Settings
    from backend.app.routes.debug import _require_dev

    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": "test-secret",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/callback",
            "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
            "ENVIRONMENT": "development",
        }
    )
    # Should not raise — guard passes when environment is development
    _require_dev(settings=settings)


def test_oauth_status_requires_auth(client: TestClient) -> None:
    """GET /api/oauth/status/{user_id} without a token must return 401."""
    response = client.get(f"/api/oauth/status/{uuid4()}")
    assert response.status_code == 401


def test_oauth_status_forbidden_for_other_user(
    authed_client: TestClient, auth_user_id: UUID
) -> None:
    """GET /api/oauth/status/{user_id} for a different user must return 403."""
    different_user_id = uuid4()
    response = authed_client.get(f"/api/oauth/status/{different_user_id}")
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied."


def test_oauth_status_returns_200_for_own_user(
    authed_client: TestClient,
    auth_user_id: UUID,
    fake_supabase,  # noqa: ANN001
) -> None:
    """GET /api/oauth/status/{user_id} for the authenticated user's own id must return 200."""
    from datetime import datetime, timezone

    from pydantic import SecretStr

    from backend.app.schemas import GmailTokens

    fake_supabase.tokens[auth_user_id] = GmailTokens(
        access_token=SecretStr("access"),
        refresh_token=SecretStr("refresh"),
        expires_at=datetime.now(timezone.utc),
    )
    response = authed_client.get(f"/api/oauth/status/{auth_user_id}")
    assert response.status_code == 200
    assert response.json()["connected"] is True
