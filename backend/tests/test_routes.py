"""Route-level tests for the FastAPI backend."""

from __future__ import annotations

from uuid import uuid4

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


def test_oauth_callback_stores_tokens(client: TestClient, fake_supabase) -> None:
    user_id = uuid4()
    payload = {"user_id": str(user_id), "code": "auth-code", "state": "state"}
    response = client.post("/api/oauth/callback", json=payload)
    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert user_id in fake_supabase.tokens


def test_list_emails_returns_items(client: TestClient) -> None:
    user_id = uuid4()
    response = client.get(f"/api/emails?user_id={user_id}")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data and len(data["items"]) == 1
    assert data["items"][0]["subject"] == "Test Message"


def test_apply_label_succeeds(client: TestClient) -> None:
    payload = {
        "user_id": str(uuid4()),
        "gmail_message_id": "msg-1",
        "label_name": "AUTO_LABEL",
    }
    response = client.post("/api/labels", json=payload)
    assert response.status_code == 200
    assert response.json()["label"] == "AUTO_LABEL"


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
