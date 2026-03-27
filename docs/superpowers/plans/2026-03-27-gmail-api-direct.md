# Gmail API Direct Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Composio middleware with direct Google Gmail API calls, eliminating a third-party dependency and giving full control over OAuth token management.

**Architecture:** A new `GmailApiAdapter` replaces `ComposioGmailAdapter` behind the existing `GmailService` abstraction — callers outside `gmail_toolkit.py` are untouched. OAuth tokens (access + refresh + expiry) are stored as real Google credentials instead of Composio connection IDs. The `GmailService` interface is preserved exactly.

**Tech Stack:** `google-auth-oauthlib`, `google-api-python-client`, `google-auth-httplib2`; remove `composio`.

**Note on MCP:** The Gmail MCP server is designed for LLM agents calling tools at runtime. Our backend is a FastAPI service that makes deterministic Gmail API calls — using MCP here would add process management overhead for no benefit. Direct library usage is correct.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app/services/gmail_toolkit.py` | Replace `ComposioGmailAdapter` with `GmailApiAdapter`; update `GmailToolkitFactory` |
| Modify | `backend/app/routes/oauth.py` | Remove Composio-managed callback branch; keep standard OAuth2 only |
| Modify | `backend/app/config.py` | Remove `composio_api_key`, `composio_account_id` |
| Modify | `backend/tests/conftest.py` | Update `FakeGmailAdapter` mock (no Composio fields) |
| Replace | `backend/tests/test_composio_adapter.py` → `backend/tests/test_gmail_adapter.py` | Rewrite tests for `GmailApiAdapter` |
| Modify | `pyproject.toml` | Remove `composio`; add `google-auth-oauthlib`, `google-api-python-client`, `google-auth-httplib2` |

---

### Task 1: Swap Dependencies

**Files:**
- Modify: `pyproject.toml` (via `uv` commands only)

- [ ] **Step 1: Remove Composio, add Google API libraries**

```bash
uv remove composio
uv add google-auth-oauthlib google-api-python-client google-auth-httplib2
```

Expected: `pyproject.toml` updated, `uv.lock` regenerated, no errors.

- [ ] **Step 2: Verify imports resolve**

```bash
uv run python -c "from google_auth_oauthlib.flow import Flow; from googleapiclient.discovery import build; print('OK')"
```

Expected output: `OK`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): replace composio with google-api-python-client"
```

---

### Task 2: Write `GmailApiAdapter` Tests (TDD)

**Files:**
- Create: `backend/tests/test_gmail_adapter.py`
- Delete: `backend/tests/test_composio_adapter.py`

- [ ] **Step 1: Delete old Composio adapter tests**

```bash
rm backend/tests/test_composio_adapter.py
```

- [ ] **Step 2: Write failing tests for `GmailApiAdapter`**

Create `backend/tests/test_gmail_adapter.py`:

```python
"""Tests for GmailApiAdapter (direct Gmail API)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.app.services.gmail_toolkit import GmailApiAdapter


ADAPTER_KWARGS = dict(
    client_id="test-client-id",
    client_secret="test-secret",
    redirect_uri="http://localhost:8000/oauth/callback",
    scopes=["https://www.googleapis.com/auth/gmail.modify"],
)


@pytest.fixture
def adapter() -> GmailApiAdapter:
    return GmailApiAdapter(**ADAPTER_KWARGS)


class TestGetAuthorizationUrl:
    def test_returns_google_url(self, adapter: GmailApiAdapter) -> None:
        url = adapter.get_authorization_url(state="abc123")
        assert "accounts.google.com" in url
        assert "abc123" in url

    def test_includes_offline_access(self, adapter: GmailApiAdapter) -> None:
        url = adapter.get_authorization_url(state="xyz")
        assert "offline" in url or "access_type=offline" in url


class TestExchangeCodeForTokens:
    def test_returns_token_dict(self, adapter: GmailApiAdapter) -> None:
        mock_creds = MagicMock()
        mock_creds.token = "access-token-123"
        mock_creds.refresh_token = "refresh-token-456"
        mock_creds.expiry = None
        mock_creds.scopes = {"https://www.googleapis.com/auth/gmail.modify"}

        mock_flow = MagicMock()
        mock_flow.credentials = mock_creds

        with patch("backend.app.services.gmail_toolkit.Flow") as mock_flow_cls:
            mock_flow_cls.from_client_config.return_value = mock_flow
            result = adapter.exchange_code_for_tokens(code="auth-code")

        assert result["access_token"] == "access-token-123"
        assert result["refresh_token"] == "refresh-token-456"
        assert result["token_type"] == "Bearer"
        mock_flow.fetch_token.assert_called_once_with(code="auth-code")


class TestListMessages:
    @pytest.fixture
    def mock_service(self) -> MagicMock:
        msg_list = MagicMock()
        msg_list.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "t1"}]
        }
        msg_get = MagicMock()
        msg_get.execute.return_value = {
            "id": "msg1",
            "threadId": "t1",
            "snippet": "Hello world",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Date", "value": "Mon, 27 Mar 2026 10:00:00 +0000"},
                ]
            },
            "labelIds": ["INBOX"],
        }
        svc = MagicMock()
        svc.users.return_value.messages.return_value.list.return_value = msg_list
        svc.users.return_value.messages.return_value.get.return_value = msg_get
        return svc

    def test_returns_message_list(self, adapter: GmailApiAdapter, mock_service: MagicMock) -> None:
        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_service):
            result = adapter.list_messages(
                access_token="tok",
                refresh_token="ref",
                max_results=10,
                query="in:inbox",
            )

        assert len(result) == 1
        assert result[0]["id"] == "msg1"
        assert result[0]["snippet"] == "Hello world"

    def test_returns_empty_on_no_messages(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_messages(
                access_token="tok", refresh_token="ref", max_results=10
            )

        assert result == []


class TestListLabels:
    def test_returns_labels(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [{"id": "Label_1", "name": "TImportant"}]
        }

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_labels(access_token="tok", refresh_token="ref")

        assert len(result) == 1
        assert result[0]["name"] == "TImportant"

    def test_returns_empty_when_no_labels(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_labels(access_token="tok", refresh_token="ref")

        assert result == []


class TestCreateLabel:
    def test_returns_label_id(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.create.return_value.execute.return_value = {
            "id": "Label_42",
            "name": "TImportant",
        }

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            label_id = adapter.create_label(
                label_name="TImportant", access_token="tok", refresh_token="ref"
            )

        assert label_id == "Label_42"

    def test_raises_on_missing_id(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.create.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            with pytest.raises(RuntimeError, match="no ID in response"):
                adapter.create_label(
                    label_name="Bad", access_token="tok", refresh_token="ref"
                )


class TestApplyLabel:
    def test_applies_important_label_and_removes_inbox(
        self, adapter: GmailApiAdapter
    ) -> None:
        mock_svc = MagicMock()
        # list labels: TImportant exists, TNotImportant exists
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "Label_1", "name": "TImportant"},
                {"id": "Label_2", "name": "TNotImportant"},
            ]
        }
        modify_call = mock_svc.users.return_value.messages.return_value.modify.return_value
        modify_call.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            adapter.apply_label(
                message_id="msg1",
                label_name="Important",
                access_token="tok",
                refresh_token="ref",
            )

        modify_call.execute.assert_called_once()
        call_body = mock_svc.users.return_value.messages.return_value.modify.call_args[1]["body"]
        assert "Label_1" in call_body["addLabelIds"]
        assert "Label_2" in call_body["removeLabelIds"]
        assert "INBOX" in call_body["removeLabelIds"]
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest backend/tests/test_gmail_adapter.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError` — `GmailApiAdapter` does not exist yet.

- [ ] **Step 4: Commit failing tests**

```bash
git add backend/tests/test_gmail_adapter.py
git rm backend/tests/test_composio_adapter.py
git commit -m "test(gmail): add failing tests for GmailApiAdapter"
```

---

### Task 3: Implement `GmailApiAdapter`

**Files:**
- Modify: `backend/app/services/gmail_toolkit.py`

- [ ] **Step 1: Replace file content**

Replace the entire `backend/app/services/gmail_toolkit.py` with:

```python
"""Adapter layer for the Gmail API (direct Google integration)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from ..config import Settings
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)

_LABEL_MAPPING = {
    "Important": "TImportant",
    "Not Important": "TNotImportant",
}
_OPPOSITE_LABEL = {
    "TImportant": "TNotImportant",
    "TNotImportant": "TImportant",
}
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailApiAdapter:
    """Direct Gmail API adapter using google-api-python-client."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes

    # ── OAuth helpers ──────────────────────────────────────────────────────

    def _flow(self) -> Flow:
        config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": _TOKEN_URI,
                "redirect_uris": [self._redirect_uri],
            }
        }
        flow = Flow.from_client_config(config, scopes=self._scopes)
        flow.redirect_uri = self._redirect_uri
        return flow

    def _credentials(self, access_token: str, refresh_token: str) -> Credentials:
        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=self._scopes,
        )

    def _service(self, access_token: str, refresh_token: str):
        creds = self._credentials(access_token, refresh_token)
        return build("gmail", "v1", credentials=creds)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_authorization_url(self, state: str) -> str:
        """Return a Google OAuth2 authorization URL."""
        url, _ = self._flow().authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )
        logger.debug("Generated authorization URL (state=%s)", state)
        return url

    def exchange_code_for_tokens(self, code: str) -> dict:
        """Exchange an authorization code for OAuth tokens.

        Returns:
            Dict with access_token, refresh_token, token_type, scope.
        """
        flow = self._flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        result: dict = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_type": "Bearer",
        }
        if creds.expiry:
            result["expires_at"] = creds.expiry.isoformat()
        if creds.scopes:
            result["scope"] = " ".join(creds.scopes)
        logger.debug("Exchanged code for tokens successfully")
        return result

    def list_messages(
        self,
        access_token: str,
        refresh_token: str,
        max_results: int = 20,
        query: str | None = None,
        user_id: str | None = None,  # kept for interface compatibility, not used
    ) -> list[dict]:
        """List Gmail messages, returning full metadata for each."""
        svc = self._service(access_token, refresh_token)
        q = query or "in:inbox"

        response = (
            svc.users()
            .messages()
            .list(userId="me", q=q, maxResults=max_results)
            .execute()
        )
        message_stubs = response.get("messages", [])
        if not message_stubs:
            return []

        messages = []
        for stub in message_stubs:
            msg = (
                svc.users()
                .messages()
                .get(
                    userId="me",
                    id=stub["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
            messages.append(msg)

        logger.info("Fetched %d messages", len(messages))
        return messages

    def get_message(
        self,
        message_id: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> dict | None:
        """Fetch a single Gmail message by ID."""
        try:
            svc = self._service(access_token, refresh_token)
            msg = (
                svc.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            logger.debug("Fetched message %s", message_id)
            return msg
        except Exception as exc:
            logger.error("Error fetching message %s: %s", message_id, exc)
            return None

    def list_labels(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> list[dict]:
        """List all Gmail labels for the authenticated user."""
        svc = self._service(access_token, refresh_token)
        response = svc.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])
        logger.debug("Found %d labels", len(labels))
        return labels

    def create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Create a Gmail label and return its ID."""
        svc = self._service(access_token, refresh_token)
        body = {
            "name": label_name,
            "messageListVisibility": "show",
            "labelListVisibility": "labelShow",
        }
        result = svc.users().labels().create(userId="me", body=body).execute()
        label_id = result.get("id")
        if not label_id:
            raise RuntimeError(f"Failed to create label '{label_name}': no ID in response")
        logger.info("Created label '%s' with ID %s", label_name, label_id)
        return str(label_id)

    def get_or_create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Return existing label ID by name, or create it."""
        labels = self.list_labels(
            access_token=access_token, refresh_token=refresh_token
        )
        for label in labels:
            if label.get("name", "").lower() == label_name.lower():
                logger.debug("Found existing label '%s' = %s", label_name, label["id"])
                return str(label["id"])

        logger.info("Label '%s' not found, creating", label_name)
        return self.create_label(
            label_name=label_name,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def apply_label(
        self,
        message_id: str,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> None:
        """Apply a classification label to a Gmail message.

        Maps "Important" → "TImportant" and "Not Important" → "TNotImportant".
        For unrecognised label names (e.g. "ai-job-alert"), applies as-is.
        Removes the opposite classification label and INBOX to archive the email.
        """
        custom_name = _LABEL_MAPPING.get(label_name, label_name)
        logger.info("Applying label '%s' to message %s", custom_name, message_id)

        label_id = self.get_or_create_label(
            label_name=custom_name,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        remove_ids: list[str] = ["INBOX"]
        opposite_name = _OPPOSITE_LABEL.get(custom_name)
        if opposite_name:
            existing = self.list_labels(
                access_token=access_token, refresh_token=refresh_token
            )
            for lbl in existing:
                if lbl.get("name") == opposite_name:
                    remove_ids.append(lbl["id"])
                    break

        svc = self._service(access_token, refresh_token)
        body = {"addLabelIds": [label_id], "removeLabelIds": remove_ids}
        svc.users().messages().modify(userId="me", id=message_id, body=body).execute()
        logger.info("✅ Applied '%s' to message %s", custom_name, message_id)


# ── Factory ───────────────────────────────────────────────────────────────


@dataclass
class GmailToolkitFactory:
    """Builds a GmailApiAdapter from application settings."""

    settings: Settings

    def build(self) -> GmailApiAdapter:
        return GmailApiAdapter(
            client_id=self.settings.google_oauth_client_id,
            client_secret=self.settings.google_oauth_client_secret.get_secret_value(),
            redirect_uri=str(self.settings.google_oauth_redirect_uri),
            scopes=[self.settings.google_oauth_scope],
        )


# ── Service (domain logic, unchanged interface) ───────────────────────────


class GmailService:
    """Domain logic around OAuth, email fetching, and label application."""

    def __init__(self, adapter: GmailApiAdapter, settings: Settings) -> None:
        self._adapter = adapter
        self._settings = settings

    async def create_authorization_url(self, state: str, user_id: str) -> str:
        logger.debug("Generating Gmail OAuth URL for user %s", user_id)
        return self._adapter.get_authorization_url(state=state)

    async def exchange_code_for_tokens(self, code: str) -> GmailTokens:
        logger.debug("Exchanging authorization code for tokens")
        raw = self._adapter.exchange_code_for_tokens(code=code)
        token_data: dict = {
            "access_token": raw["access_token"],
            "refresh_token": raw["refresh_token"],
            "token_type": raw.get("token_type", "Bearer"),
        }
        if raw.get("expires_at"):
            token_data["expires_at"] = raw["expires_at"]
        if raw.get("scope"):
            token_data["scope"] = raw["scope"]
        return GmailTokens(**token_data)

    async def list_messages(
        self,
        tokens: GmailTokens,
        user_id: str,
        max_results: int = 20,
        query: str | None = None,
    ) -> list[dict]:
        return self._adapter.list_messages(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            max_results=max_results,
            query=query,
            user_id=user_id,
        )

    async def list_labels(self, tokens: GmailTokens, user_id: str) -> list[dict]:
        return self._adapter.list_labels(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )

    async def apply_label(
        self,
        message_id: str,
        label_id: str,
        tokens: GmailTokens,
        user_id: str,
    ) -> None:
        self._adapter.apply_label(
            message_id=message_id,
            label_name=label_id,
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )
```

- [ ] **Step 2: Run the new tests — they should now pass**

```bash
uv run pytest backend/tests/test_gmail_adapter.py -v
```

Expected: All tests **PASS**.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
uv run pytest backend/tests/ -v --ignore=backend/tests/test_gmail_adapter.py 2>&1 | tail -20
```

Fix any failures before proceeding.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/gmail_toolkit.py
git commit -m "feat(gmail): replace ComposioGmailAdapter with GmailApiAdapter"
```

---

### Task 4: Simplify OAuth Callback Route

**Files:**
- Modify: `backend/app/routes/oauth.py`

The current callback handles two branches: Composio-managed (`connected_account_id`) and standard OAuth2 (`code`). Remove the Composio branch.

- [ ] **Step 1: Write a failing test for the simplified callback**

Add to `backend/tests/test_routes.py` (or the existing OAuth test file):

```python
async def test_oauth_callback_rejects_missing_code(async_client: AsyncClient) -> None:
    """Callback without a code should return 400."""
    response = await async_client.post("/oauth/callback", json={
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "test@example.com",
        # no 'code' field
    })
    assert response.status_code == 400


async def test_oauth_callback_with_code_stores_tokens(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Valid code exchange stores tokens and returns success."""
    from backend.app.services.gmail_toolkit import GmailService

    async def fake_exchange(code: str) -> GmailTokens:
        return GmailTokens(
            access_token="acc",
            refresh_token="ref",
            token_type="Bearer",
        )

    monkeypatch.setattr(GmailService, "exchange_code_for_tokens", fake_exchange)

    response = await async_client.post("/oauth/callback", json={
        "user_id": "00000000-0000-0000-0000-000000000001",
        "email": "test@example.com",
        "code": "valid-auth-code",
        "state": "random-state",
    })
    assert response.status_code == 200
    assert response.json()["success"] is True
```

- [ ] **Step 2: Run to verify they fail**

```bash
uv run pytest backend/tests/test_routes.py -v -k "callback" 2>&1 | tail -20
```

- [ ] **Step 3: Update `oauth.py` callback**

Read the current `backend/app/routes/oauth.py`, then replace the `OAuthCallbackRequest` model and callback handler to remove the Composio branch:

```python
class OAuthCallbackRequest(BaseModel):
    user_id: UUID
    email: EmailStr
    code: str  # required — standard OAuth2 code
    state: str | None = None
```

And the callback handler body becomes:

```python
@router.post("/callback", response_model=OAuthCallbackResponse)
async def oauth_callback(
    request: OAuthCallbackRequest,
    gmail_service: GmailService = Depends(get_gmail_service),
    db: DBService = Depends(get_db_service),
) -> OAuthCallbackResponse:
    """Handle OAuth2 callback and persist tokens."""
    tokens = await gmail_service.exchange_code_for_tokens(request.code)
    await db.store_gmail_tokens(request.user_id, tokens)
    logger.info("Stored Gmail tokens for user %s", request.user_id)
    return OAuthCallbackResponse(success=True, user_id=request.user_id)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest backend/tests/test_routes.py -v 2>&1 | tail -20
```

Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routes/oauth.py backend/tests/test_routes.py
git commit -m "refactor(oauth): remove Composio callback branch, use standard OAuth2 only"
```

---

### Task 5: Clean Up Config

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Remove Composio fields from `Settings`**

In `backend/app/config.py`, delete these two fields:

```python
composio_api_key: SecretStr
composio_account_id: str
```

- [ ] **Step 2: Run tests to confirm nothing references them**

```bash
uv run pytest backend/tests/ -v 2>&1 | tail -20
```

If tests fail referencing `composio_api_key` in `conftest.py`, remove those keys from the test settings override too.

- [ ] **Step 3: Update `conftest.py` if needed**

In `backend/tests/conftest.py`, find any test settings dict that includes `COMPOSIO_API_KEY` or `COMPOSIO_ACCOUNT_ID` and remove those keys.

- [ ] **Step 4: Run full suite**

```bash
uv run pytest backend/tests/ -v 2>&1 | tail -30
```

Expected: All tests pass.

- [ ] **Step 5: Lint**

```bash
uv run ruff check backend/ --fix && uv run ruff format backend/
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/tests/conftest.py
git commit -m "chore(config): remove Composio configuration fields"
```

---

## Self-Review

**Spec coverage:**
- ✅ Remove Composio dependency → Task 1 removes it, Task 3 replaces the adapter
- ✅ Use Gmail API directly → `GmailApiAdapter` uses `google-api-python-client`
- ✅ MCP evaluated → documented in plan header (not appropriate for backend service)
- ✅ OAuth flow works → Task 4 simplifies callback
- ✅ Callers unaffected → `GmailService` interface identical

**Placeholder scan:** None found — all steps have complete code.

**Type consistency:**
- `GmailApiAdapter` is consistent throughout
- `GmailToolkitFactory.build()` returns `GmailApiAdapter` (not `ComposioGmailAdapter`)
- `GmailService.__init__` takes `GmailApiAdapter` (same interface, different class name)
- All `apply_label` calls pass `label_name` string, same as before
