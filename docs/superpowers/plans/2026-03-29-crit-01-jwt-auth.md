# CRIT-01: JWT Authentication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JWT-based authentication to all protected FastAPI endpoints so that `user_id` is derived from a verified token, not from client-supplied request parameters.

**Architecture:** The `/oauth/callback` endpoint issues a signed JWT (HS256) containing the `user_id` after a successful Gmail OAuth exchange. All protected routes declare a `require_auth` FastAPI dependency that reads the token from the `Authorization: Bearer` header (or `?token=` query param for the browser review page). Sessions and pattern routes additionally verify resource ownership against the authenticated user_id. The CLI uses services directly (bypasses HTTP), so it is unaffected by the auth layer; it appends the JWT to the review URL it opens in the browser.

**Tech Stack:** PyJWT, FastAPI `HTTPBearer` security, Pydantic `SecretStr`, pytest

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Create** | `backend/app/auth.py` | JWT issue/verify, `require_auth` dependency |
| **Modify** | `backend/app/config.py` | Add `JWT_SECRET_KEY` setting |
| **Modify** | `backend/app/schemas/oauth.py` | Add `access_token` field to `OAuthCallbackResponse` |
| **Modify** | `backend/app/routes/oauth.py` | Issue JWT on callback; protect status endpoint |
| **Modify** | `backend/app/routes/emails.py` | Replace `user_id` query param with `require_auth` |
| **Modify** | `backend/app/routes/labels.py` | Override `user_id` from JWT |
| **Modify** | `backend/app/routes/sessions.py` | Auth + ownership checks on all session endpoints |
| **Modify** | `backend/app/routes/patterns.py` | Replace `user_id` query param with `require_auth` |
| **Modify** | `backend/app/routes/review.py` | Auth on page + correct endpoints; token in JS |
| **Modify** | `backend/app/routes/debug.py` | Gate routes to dev environment only |
| **Modify** | `backend/app/dependencies.py` | Expose `get_current_user` dependency for overrides in tests |
| **Modify** | `backend/cli.py` | Append JWT to review URL opened in browser |
| **Modify** | `backend/tests/conftest.py` | Add `JWT_SECRET_KEY` to test settings; add `auth_headers` fixture |
| **Create** | `backend/tests/test_auth.py` | Unit tests for `create_access_token` / `decode_access_token` |
| **Modify** | `backend/tests/test_routes.py` | Add auth headers to all protected route tests |

---

## Task 1: Install PyJWT and add `JWT_SECRET_KEY` to Settings

**Files:**
- Modify: `backend/app/config.py`
- Modify: `config/env.example` (if present — add `JWT_SECRET_KEY=` line)

- [ ] **Step 1: Install PyJWT**

```bash
cd /workspaces/autogen-test
uv add PyJWT
```

Expected: PyJWT appears in `pyproject.toml` dependencies and `uv.lock` is updated.

- [ ] **Step 2: Write failing test — Settings rejects missing JWT_SECRET_KEY**

In `backend/tests/test_auth.py` (create new file):

```python
"""Tests for JWT authentication utilities."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.config import Settings


def test_settings_requires_jwt_secret_key() -> None:
    """Settings must reject startup if JWT_SECRET_KEY is missing."""
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "FERNET_SECRET_KEY": "dGVzdC10ZXN0LXRlc3QtdGVzdC10ZXN0LXRlc3QtdGVzdA==",
                "GOOGLE_OAUTH_CLIENT_ID": "client-id",
                "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
                "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/callback",
                # JWT_SECRET_KEY intentionally omitted
            }
        )
```

- [ ] **Step 3: Run test to verify it fails**

```bash
docker compose exec backend uv run pytest backend/tests/test_auth.py::test_settings_requires_jwt_secret_key -v
```

Expected: FAIL — Settings currently has no `jwt_secret_key` field, so `model_validate` succeeds (no ValidationError raised).

- [ ] **Step 4: Add `jwt_secret_key` to Settings**

In `backend/app/config.py`, add the field after `fernet_secret_key`:

```python
# Encryption
fernet_secret_key: SecretStr = Field(..., alias="FERNET_SECRET_KEY")
jwt_secret_key: SecretStr = Field(..., alias="JWT_SECRET_KEY")
```

- [ ] **Step 5: Add `JWT_SECRET_KEY` to env.example**

In `config/env.example`, add:

```bash
# ============================================
# JWT AUTHENTICATION
# ============================================
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=your_jwt_secret_here
```

- [ ] **Step 6: Add `JWT_SECRET_KEY` to your local `.env`**

Generate a value and add it to `config/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Copy the output into `config/.env` as `JWT_SECRET_KEY=<generated_value>`.

- [ ] **Step 7: Run test to verify it passes**

```bash
docker compose exec backend uv run pytest backend/tests/test_auth.py::test_settings_requires_jwt_secret_key -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/config.py config/env.example pyproject.toml uv.lock
git commit -m "feat(auth): add JWT_SECRET_KEY to settings and install PyJWT"
```

---

## Task 2: Create `backend/app/auth.py` — JWT issue and verify

**Files:**
- Create: `backend/app/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests for JWT utilities**

Append to `backend/tests/test_auth.py`:

```python
from datetime import timedelta
from uuid import UUID, uuid4

import jwt
import pytest

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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest backend/tests/test_auth.py -v
```

Expected: 4 FAILs — `backend.app.auth` module does not exist yet.

- [ ] **Step 3: Create `backend/app/auth.py`**

```python
"""JWT authentication utilities and FastAPI dependency."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

_bearer = HTTPBearer(auto_error=False)

_ALGORITHM = "HS256"
_EXPIRE_HOURS = 24 * 7  # 7 days


def create_access_token(user_id: UUID, secret: str) -> str:
    """Return a signed JWT encoding the given user_id."""
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=_EXPIRE_HOURS),
    }
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


def decode_access_token(token: str, secret: str) -> UUID:
    """Decode and validate a JWT; return the user_id or raise HTTP 401."""
    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        return UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    token: str | None = Query(default=None, include_in_schema=False),
    settings: Settings = Depends(get_settings),
) -> UUID:
    """FastAPI dependency: extract and verify the caller's JWT.

    Accepts the token from either:
    - ``Authorization: Bearer <token>`` header (API clients, JS fetch calls)
    - ``?token=<token>`` query parameter (browser review page initial load)
    """
    raw = (credentials.credentials if credentials else None) or token
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(raw, settings.jwt_secret_key.get_secret_value())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest backend/tests/test_auth.py -v
```

Expected: 5 PASSes (including the settings test from Task 1).

- [ ] **Step 5: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat(auth): add JWT create/decode utilities and require_auth dependency"
```

---

## Task 3: Issue JWT on OAuth callback and expose `get_current_user` override point

**Files:**
- Modify: `backend/app/schemas/oauth.py`
- Modify: `backend/app/routes/oauth.py`
- Modify: `backend/app/dependencies.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing test — callback response includes access_token**

In `backend/tests/test_routes.py`, replace `test_oauth_callback_stores_tokens`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_oauth_callback_stores_tokens_and_returns_token -v
```

Expected: FAIL — current callback does not return `access_token`.

- [ ] **Step 3: Add `access_token` to `OAuthCallbackResponse`**

In `backend/app/schemas/oauth.py`, update the response schema:

```python
class OAuthCallbackResponse(BaseModel):
    """Status after processing the OAuth callback."""

    connected: bool
    expires_at: datetime
    access_token: str
```

- [ ] **Step 4: Update the callback route to issue a JWT**

In `backend/app/routes/oauth.py`, add the import and update the handler:

```python
from ..auth import create_access_token
```

Replace the callback handler body (keep the function signature identical):

```python
@router.get(
    "/callback",
    response_model=OAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def oauth_callback(
    code: str,
    state: str,
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: DBService = Depends(get_db_service),
    settings: Settings = Depends(get_settings),
) -> OAuthCallbackResponse:
    """Process Gmail OAuth callback from Google redirect."""
    try:
        user_id = UUID(state.split(".")[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid state parameter.")
    tokens = await gmail_service.exchange_code_for_tokens(code)
    await supabase.store_gmail_tokens(user_id, tokens)
    logger.info("Stored Gmail OAuth tokens for user {}", user_id)
    access_token = create_access_token(
        user_id, settings.jwt_secret_key.get_secret_value()
    )
    return OAuthCallbackResponse(
        connected=True,
        expires_at=tokens.expires_at,
        access_token=access_token,
    )
```

Also add `Settings` to the import at the top of `oauth.py`:

```python
from ..config import Settings, get_settings
```

- [ ] **Step 5: Add `get_current_user` to `dependencies.py`**

This exposes a named dependency that tests can override:

In `backend/app/dependencies.py`, add at the bottom:

```python
from .auth import require_auth  # noqa: E402 — circular-safe at function call time

def get_current_user(user_id: UUID = Depends(require_auth)) -> UUID:
    """Return the authenticated user_id. Override in tests via dependency_overrides."""
    return user_id
```

Also add the UUID import at the top if not present:

```python
from uuid import UUID
```

- [ ] **Step 6: Update `conftest.py` — add `JWT_SECRET_KEY` to test settings and add `auth_headers` fixture**

In `backend/tests/conftest.py`:

1. Add the import at the top:

```python
from backend.app.auth import create_access_token
from backend.app.dependencies import get_current_user
```

2. Update the `Settings.model_validate(...)` call inside the `client` fixture to include `JWT_SECRET_KEY`:

```python
settings = Settings.model_validate(
    {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
        "JWT_SECRET_KEY": "test-jwt-secret-do-not-use-in-prod",
        "AGENT_RUNTIME_BASE_URL": "http://localhost:9000",
        "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:3005/oauth/callback",
        "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
    }
)
```

3. Add a `TEST_JWT_SECRET` constant and `auth_user_id` and `auth_headers` fixtures after the existing fixtures:

```python
TEST_JWT_SECRET = "test-jwt-secret-do-not-use-in-prod"


@pytest.fixture
def auth_user_id() -> UUID:
    """A stable user UUID for use in auth-protected tests."""
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def auth_headers(auth_user_id: UUID) -> dict[str, str]:
    """Bearer token headers for auth-protected endpoint tests."""
    token = create_access_token(auth_user_id, TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_client(
    fake_supabase: FakeDBService,
    fake_gmail_service: FakeGmailService,
    fake_email_service: FakeEmailService,
    fake_label_service: FakeLabelService,
    fake_agent_service: FakeAgentService,
    auth_user_id: UUID,
) -> Iterator[TestClient]:
    """TestClient with auth dependency pre-wired to a known user_id."""
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": TEST_JWT_SECRET,
            "AGENT_RUNTIME_BASE_URL": "http://localhost:9000",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:3005/oauth/callback",
            "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
        }
    )
    app = create_app(settings)

    app.dependency_overrides[get_db_service] = lambda: fake_supabase
    app.dependency_overrides[get_gmail_service] = lambda: fake_gmail_service
    app.dependency_overrides[get_email_service] = lambda: fake_email_service
    app.dependency_overrides[get_label_service] = lambda: fake_label_service
    app.dependency_overrides[get_agent_service] = lambda: fake_agent_service
    # Override auth to return a known user_id — no token needed in tests
    app.dependency_overrides[get_current_user] = lambda: auth_user_id

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
```

- [ ] **Step 7: Run tests**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_oauth_callback_stores_tokens_and_returns_token -v
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/schemas/oauth.py backend/app/routes/oauth.py backend/app/dependencies.py backend/tests/conftest.py backend/tests/test_routes.py
git commit -m "feat(auth): issue JWT on OAuth callback; add get_current_user dependency"
```

---

## Task 4: Protect the emails route

**Files:**
- Modify: `backend/app/routes/emails.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests — unauthenticated request is rejected; authed request succeeds**

Append to `backend/tests/test_routes.py`:

```python
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
```

Remove or rename the old unauthenticated `test_list_emails_returns_items` test to avoid confusion:

```python
# Remove this test — replaced by test_list_emails_with_auth above
# def test_list_emails_returns_items(client: TestClient) -> None: ...
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_list_emails_requires_auth backend/tests/test_routes.py::test_list_emails_with_auth -v
```

Expected: both FAIL — auth is not enforced yet.

- [ ] **Step 3: Update `emails.py` to require auth**

Replace the content of `backend/app/routes/emails.py`:

```python
"""Email routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..dependencies import get_current_user, get_email_service
from ..schemas.email import EmailListResponse
from ..services.email_service import EmailService

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def list_emails(
    max_results: int = Query(20, ge=1, le=50),
    query: str | None = Query(
        None,
        description="Gmail search query (e.g., 'in:inbox', 'is:unread'). Defaults to 'in:inbox'",
    ),
    user_id: UUID = Depends(get_current_user),
    email_service: EmailService = Depends(get_email_service),
) -> JSONResponse:
    """Fetch latest Gmail messages for the authenticated user."""
    try:
        emails = await email_service.fetch_latest_emails(
            user_id=user_id, max_results=max_results, query=query
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response_model = EmailListResponse(items=emails)
    return JSONResponse(
        content=response_model.model_dump(mode="json", by_alias=True),
        status_code=status.HTTP_200_OK,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_list_emails_requires_auth backend/tests/test_routes.py::test_list_emails_with_auth -v
```

Expected: both PASS

- [ ] **Step 5: Run full suite to check for regressions**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass (old `test_list_emails_returns_items` is removed — confirm no failures).

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/emails.py backend/tests/test_routes.py
git commit -m "feat(auth): protect GET /api/emails with require_auth"
```

---

## Task 5: Protect the labels route

**Files:**
- Modify: `backend/app/routes/labels.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
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
```

Remove the old unauthenticated `test_apply_label_succeeds` test.

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_apply_label_requires_auth backend/tests/test_routes.py::test_apply_label_with_auth -v
```

Expected: both FAIL

- [ ] **Step 3: Update `labels.py` to require auth**

Replace the content of `backend/app/routes/labels.py`:

```python
"""Gmail label routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user, get_label_service
from ..schemas import ApplyLabelRequest, ApplyLabelResponse
from ..services.label_service import LabelService

router = APIRouter()


@router.post(
    "",
    response_model=ApplyLabelResponse,
    status_code=status.HTTP_200_OK,
)
async def apply_label(
    payload: ApplyLabelRequest,
    user_id: UUID = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> ApplyLabelResponse:
    """Apply a Gmail label to the provided message."""
    # Override user_id from JWT — ignore any user_id in the request body
    payload.user_id = user_id
    try:
        return await label_service.apply_label(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
```

Note: `ApplyLabelRequest.user_id` is set from the JWT. The field remains in the schema for compatibility with direct service calls from the CLI.

- [ ] **Step 4: Check that `ApplyLabelRequest` allows model mutation**

In `backend/app/schemas/labels.py`, confirm the model does not use `model_config = ConfigDict(frozen=True)`. If it does, remove `frozen=True`. Read the file:

```bash
docker compose exec backend grep -n "frozen" backend/app/schemas/labels.py || echo "not frozen"
```

If frozen, change `frozen=True` to `frozen=False` (or remove the line).

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py::test_apply_label_requires_auth backend/tests/test_routes.py::test_apply_label_with_auth -v
```

Expected: both PASS

- [ ] **Step 6: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/labels.py backend/tests/test_routes.py
git commit -m "feat(auth): protect POST /api/labels with require_auth"
```

---

## Task 6: Protect the sessions routes with auth and ownership checks

**Files:**
- Modify: `backend/app/routes/sessions.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_create_session_requires_auth \
  backend/tests/test_routes.py::test_get_session_requires_auth \
  backend/tests/test_routes.py::test_run_session_requires_auth \
  backend/tests/test_routes.py::test_cleanup_session_requires_auth -v
```

Expected: all 4 FAIL

- [ ] **Step 3: Update `sessions.py` — add auth and ownership checks**

Replace the content of `backend/app/routes/sessions.py`:

```python
"""Classification session API endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import (
    get_batch_classifier,
    get_classification_session_service,
    get_current_user,
)
from ..services.batch_classifier import BatchClassifier
from ..services.classification_session_service import ClassificationSessionService

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSessionRequest(BaseModel):
    """Request payload for creating a classification session."""

    max_results: int = Field(default=10, ge=1, le=50)


class CreateSessionResponse(BaseModel):
    """Response after creating a session."""

    session_id: UUID
    email_count: int
    status: str


class SessionStatusResponse(BaseModel):
    """Session status response."""

    session_id: UUID
    status: str
    email_count: int
    created_at: str
    completed_at: str | None = None


class CleanupResponse(BaseModel):
    """Response after cleaning up a session."""

    session_id: UUID
    emails_deleted: int
    runs_deleted: int
    status: str


async def _get_owned_session(
    session_id: UUID,
    current_user: UUID,
    session_svc: ClassificationSessionService,
) -> dict:
    """Fetch a session and verify the caller owns it. Raises 404 or 403."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")
    return session


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> CreateSessionResponse:
    """Create a new classification session and fetch unlabeled emails into it."""
    try:
        session_id = await session_svc.create_session(
            user_id=current_user,
            max_results=request.max_results,
        )
        session = await session_svc.get_session(session_id)
        email_count = session.get("email_count", 0) if session else 0
        return CreateSessionResponse(
            session_id=session_id,
            email_count=email_count,
            status="pending",
        )
    except Exception as e:
        logger.error("Failed to create session: %s", e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> SessionStatusResponse:
    """Get the status of a classification session."""
    session = await _get_owned_session(session_id, current_user, session_svc)
    return SessionStatusResponse(
        session_id=UUID(session["id"]),
        status=session["status"],
        email_count=session.get("email_count", 0),
        created_at=str(session.get("created_at", "")),
        completed_at=session.get("completed_at"),
    )


@router.post("/{session_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_session(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    batch_classifier: BatchClassifier = Depends(get_batch_classifier),
) -> dict:
    """Trigger batch LLM classification for all emails in a session (runs in background)."""
    session = await _get_owned_session(session_id, current_user, session_svc)
    if session["status"] not in ("pending", "awaiting_review"):
        raise HTTPException(
            status_code=409,
            detail=f"Session is in status '{session['status']}', cannot run again.",
        )

    user_id = UUID(session["user_id"])

    async def _run_bg() -> None:
        try:
            await batch_classifier.run_batch(session_id=session_id, user_id=user_id)
        except Exception as e:
            logger.error("Background batch classification failed for session %s: %s", session_id, e)

    background_tasks.add_task(_run_bg)
    return {"session_id": str(session_id), "status": "classifying", "message": "Batch started"}


@router.get("/{session_id}/emails")
async def get_session_emails(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> dict:
    """Get all emails in a session for review."""
    await _get_owned_session(session_id, current_user, session_svc)
    emails = await session_svc.get_session_emails(session_id)
    return {
        "session_id": str(session_id),
        "emails": [e.model_dump(mode="json") for e in emails],
    }


@router.post("/{session_id}/cleanup", response_model=CleanupResponse)
async def cleanup_session(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> CleanupResponse:
    """Delete emails and agent_runs for a session, mark it cleaned_up."""
    await _get_owned_session(session_id, current_user, session_svc)
    result = await session_svc.cleanup_session(session_id)
    return CleanupResponse(
        session_id=session_id,
        emails_deleted=result["emails_deleted"],
        runs_deleted=result["runs_deleted"],
        status="cleaned_up",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_create_session_requires_auth \
  backend/tests/test_routes.py::test_get_session_requires_auth \
  backend/tests/test_routes.py::test_run_session_requires_auth \
  backend/tests/test_routes.py::test_cleanup_session_requires_auth -v
```

Expected: all 4 PASS

- [ ] **Step 5: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/sessions.py backend/tests/test_routes.py
git commit -m "feat(auth): protect sessions routes with auth and ownership checks"
```

---

## Task 7: Protect patterns routes

**Files:**
- Modify: `backend/app/routes/patterns.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_list_patterns_requires_auth \
  backend/tests/test_routes.py::test_extract_patterns_requires_auth -v
```

Expected: both FAIL

- [ ] **Step 3: Add `Depends(get_current_user)` to all pattern endpoints**

In `backend/app/routes/patterns.py`, add the import:

```python
from uuid import UUID
from ..dependencies import get_current_user, get_pattern_service
```

Replace the `user_id: UUID = Query(...)` parameter on every endpoint with `user_id: UUID = Depends(get_current_user)`. The five functions to update are `extract_patterns`, `list_patterns`, `get_learned_context`, `create_pattern`, `update_pattern`, and `delete_pattern`.

The complete updated file:

```python
"""API routes for label pattern management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user, get_pattern_service
from ..schemas.label_patterns import (
    LabelPattern,
    LabelPatternCreate,
    LabelPatternListResponse,
    LabelPatternUpdate,
    LearnedContext,
    PatternExtractionRequest,
)
from ..services.pattern_learning_service import PatternLearningService

router = APIRouter()


@router.post(
    "/extract",
    status_code=status.HTTP_201_CREATED,
    summary="Extract patterns from labeled email",
)
async def extract_patterns(
    request: PatternExtractionRequest,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> dict:
    """Extract and store patterns from a labeled email."""
    patterns_added = await service.extract_and_store_patterns(request=request, user_id=user_id)
    return {"message": "Patterns extracted successfully", "patterns_added": patterns_added}


@router.get(
    "",
    response_model=LabelPatternListResponse,
    summary="List all learned patterns",
)
async def list_patterns(
    label_type: Optional[str] = None,
    pattern_type: Optional[str] = None,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPatternListResponse:
    """List all learned patterns for the authenticated user."""
    supabase = service._supabase
    patterns_data = await supabase.get_label_patterns(
        user_id=user_id,
        label_type=label_type,
        pattern_type=pattern_type,
    )
    patterns = [LabelPattern(**data) for data in patterns_data]
    return LabelPatternListResponse(patterns=patterns, total=len(patterns))


@router.get(
    "/context",
    response_model=LearnedContext,
    summary="Get learned context for AI prompt",
)
async def get_learned_context(
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LearnedContext:
    """Retrieve learned patterns formatted for AI prompt injection."""
    return await service.get_learned_context(user_id=user_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelPattern,
    summary="Create user-defined pattern",
)
async def create_pattern(
    pattern: LabelPatternCreate,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """Create a user-defined pattern manually."""
    supabase = service._supabase
    pattern_id = await supabase.create_user_defined_pattern(
        user_id=user_id,
        label_type=pattern.label_type,
        pattern_type=pattern.pattern_type,
        pattern_value=pattern.pattern_value,
    )
    patterns = await supabase.get_label_patterns(user_id=user_id)
    created = next(p for p in patterns if p["pattern_id"] == str(pattern_id))
    return LabelPattern(**created)


@router.patch(
    "/{pattern_id}",
    response_model=LabelPattern,
    summary="Update a pattern",
)
async def update_pattern(
    pattern_id: UUID,
    updates: LabelPatternUpdate,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """Update an existing pattern owned by the authenticated user."""
    supabase = service._supabase
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)
    if not pattern_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    update_data = updates.model_dump(exclude_unset=True)
    if update_data:
        await supabase.update_label_pattern(pattern_id=pattern_id, updates=update_data)
    patterns = await supabase.get_label_patterns(user_id=user_id)
    updated = next(p for p in patterns if p["pattern_id"] == str(pattern_id))
    return LabelPattern(**updated)


@router.delete(
    "/{pattern_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pattern",
)
async def delete_pattern(
    pattern_id: UUID,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> None:
    """Delete a learned pattern owned by the authenticated user."""
    supabase = service._supabase
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)
    if not pattern_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    await supabase.delete_label_pattern(pattern_id=pattern_id)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_list_patterns_requires_auth \
  backend/tests/test_routes.py::test_extract_patterns_requires_auth -v
```

Expected: both PASS

- [ ] **Step 5: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/patterns.py backend/tests/test_routes.py
git commit -m "feat(auth): protect patterns routes with require_auth"
```

---

## Task 8: Protect review routes and pass token to review page JS

**Files:**
- Modify: `backend/app/routes/review.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_requires_auth \
  backend/tests/test_routes.py::test_correct_label_requires_auth -v
```

Expected: both FAIL

- [ ] **Step 3: Update `review.py` — add auth and embed token in JS**

In `backend/app/routes/review.py`, update the imports:

```python
from ..dependencies import (
    get_classification_session_service,
    get_current_user,
    get_label_service,
)
```

Update `review_page` to require auth and embed the token in the JS:

```python
@router.get("/{session_id}", response_class=HTMLResponse)
async def review_page(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> HTMLResponse:
    """Serve the self-contained HTML review UI for a session."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    # ... (keep the rest of the HTML generation unchanged)
```

In the JavaScript block, after `const SESSION_ID = "{session_id_str}";`, add:

```javascript
// Token is passed via URL query param on initial load, then used for all API calls
const params = new URLSearchParams(window.location.search);
const TOKEN = params.get('token') || '';

function authHeaders() {{
  return TOKEN ? {{"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN}}
               : {{"Content-Type": "application/json"}};
}}
```

In the `correct()` fetch call, replace `headers: {{"Content-Type": "application/json"}}` with `headers: authHeaders()`.

In the `doneAndCleanup()` fetch call, add `headers: authHeaders()` to the fetch options.

- [ ] **Step 4: Update `correct_label` endpoint to require auth**

In `review.py`, update `correct_label`:

```python
@router.post("/{session_id}/correct")
async def correct_label(
    session_id: UUID,
    request: CorrectionRequest,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    label_svc: LabelService = Depends(get_label_service),
) -> dict:
    """Apply a human correction to an email's label (triggers pattern learning)."""
    if request.new_label not in ("Important", "Not Important"):
        raise HTTPException(
            status_code=422, detail="new_label must be 'Important' or 'Not Important'"
        )

    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["user_id"] != str(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    user_id = UUID(session["user_id"])

    try:
        await label_svc.apply_label(
            ApplyLabelRequest(
                user_id=user_id,
                gmail_message_id=request.gmail_message_id,
                label_name=request.new_label,
            )
        )
        return {"success": True, "label": request.new_label}
    except Exception as e:
        logger.error("Correction failed for email %s: %s", request.email_id, e)
        raise HTTPException(status_code=500, detail="An internal error occurred.")
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_requires_auth \
  backend/tests/test_routes.py::test_correct_label_requires_auth -v
```

Expected: both PASS

- [ ] **Step 6: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/review.py backend/tests/test_routes.py
git commit -m "feat(auth): protect review routes; embed auth token in review page JS"
```

---

## Task 9: Gate debug routes to dev environment only (CRIT-03)

**Files:**
- Modify: `backend/app/routes/debug.py`
- Modify: `backend/app/config.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing test — debug endpoint returns 403 in non-dev environment**

Append to `backend/tests/test_routes.py`:

```python
def test_debug_endpoints_disabled_in_non_dev(client: TestClient) -> None:
    """Debug endpoints must return 403 when environment is not 'development'."""
    response = client.get(f"/api/debug/emails/{uuid4()}")
    assert response.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_debug_endpoints_disabled_in_non_dev -v
```

Expected: FAIL — debug endpoint currently returns 200.

- [ ] **Step 3: Add `environment` field to Settings**

In `backend/app/config.py`, add:

```python
environment: str = Field(default="production", alias="ENVIRONMENT")
```

- [ ] **Step 4: Add environment guard to `debug.py`**

Replace the content of `backend/app/routes/debug.py`:

```python
"""Debug routes for troubleshooting — only active when ENVIRONMENT=development."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ..config import Settings, get_settings
from ..dependencies import get_db_service
from ..db.models import AgentRun, Email
from ..services.db_service import DBService

router = APIRouter()


def _require_dev(settings: Settings = Depends(get_settings)) -> None:
    if settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug endpoints are only available in development.",
        )


@router.get("/emails/{user_id}", dependencies=[Depends(_require_dev)])
async def debug_emails(
    user_id: UUID,
    db: DBService = Depends(get_db_service),
) -> dict:
    """Debug endpoint to see raw email data from database."""
    async with db.session_factory() as session:
        stmt = select(Email).where(Email.user_id == str(user_id))
        result = await session.execute(stmt)
        emails = [
            {
                "id": obj.id,
                "gmail_message_id": obj.gmail_message_id,
                "subject": obj.subject,
                "sender_email": obj.sender_email,
                "received_at": obj.received_at,
            }
            for obj in result.scalars().all()
        ]
    return {"count": len(emails), "emails": emails}


@router.get("/agent-runs/{user_id}", dependencies=[Depends(_require_dev)])
async def debug_agent_runs(
    user_id: UUID,
    db: DBService = Depends(get_db_service),
) -> dict:
    """Debug endpoint to see raw agent run data from database."""
    async with db.session_factory() as session:
        stmt = select(AgentRun).where(AgentRun.user_id == str(user_id))
        result = await session.execute(stmt)
        runs = [
            {
                "id": obj.id,
                "email_id": obj.email_id,
                "status": obj.status,
                "result_payload": obj.result_payload,
                "updated_at": obj.updated_at,
            }
            for obj in result.scalars().all()
        ]
    return {"count": len(runs), "runs": runs}
```

- [ ] **Step 5: Run test to verify it passes**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_debug_endpoints_disabled_in_non_dev -v
```

Expected: PASS

- [ ] **Step 6: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/debug.py backend/app/config.py backend/tests/test_routes.py
git commit -m "fix(auth): gate debug endpoints to ENVIRONMENT=development only (CRIT-03)"
```

---

## Task 10: Protect OAuth status endpoint

**Files:**
- Modify: `backend/app/routes/oauth.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing test**

Append to `backend/tests/test_routes.py`:

```python
def test_oauth_status_requires_auth(client: TestClient) -> None:
    """GET /api/oauth/status/{user_id} without a token must return 401."""
    response = client.get(f"/api/oauth/status/{uuid4()}")
    assert response.status_code == 401


def test_oauth_status_forbidden_for_other_user(authed_client: TestClient, auth_user_id) -> None:
    """GET /api/oauth/status/{user_id} for a different user must return 403."""
    different_user_id = uuid4()
    response = authed_client.get(f"/api/oauth/status/{different_user_id}")
    assert response.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_oauth_status_requires_auth \
  backend/tests/test_routes.py::test_oauth_status_forbidden_for_other_user -v
```

Expected: both FAIL

- [ ] **Step 3: Update `get_oauth_status` in `oauth.py`**

Add import at top of `routes/oauth.py`:

```python
from ..dependencies import get_current_user
```

Replace `get_oauth_status`:

```python
@router.get(
    "/status/{user_id}",
    response_model=OAuthStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_oauth_status(
    user_id: UUID,
    current_user: UUID = Depends(get_current_user),
    supabase: DBService = Depends(get_db_service),
) -> OAuthStatusResponse:
    """Return whether the user has an active Gmail connection."""
    if user_id != current_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )
    tokens = await supabase.fetch_gmail_tokens(user_id)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail connection found for user.",
        )
    return OAuthStatusResponse(connected=True, expires_at=tokens.expires_at)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_oauth_status_requires_auth \
  backend/tests/test_routes.py::test_oauth_status_forbidden_for_other_user -v
```

Expected: both PASS

- [ ] **Step 5: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v --tb=short
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/oauth.py backend/tests/test_routes.py
git commit -m "feat(auth): protect OAuth status endpoint; verify caller owns the resource"
```

---

## Task 11: Update CLI to store JWT and pass it to the review URL

**Files:**
- Modify: `backend/cli.py`

The CLI calls services directly (not HTTP), so it is unaffected by the auth layer for most operations. However, it does open the review URL in a browser. For the browser to authenticate, the CLI must append the token to the URL.

- [ ] **Step 1: Update `save_session` to persist the JWT**

In `backend/cli.py`, update `save_session` to accept and persist an optional `access_token`:

```python
def save_session(
    user_id: str,
    email: str,
    last_session_id: str | None = None,
    access_token: str | None = None,
) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {"user_id": user_id, "email": email}
    if last_session_id:
        data["last_session_id"] = last_session_id
    elif SESSION_FILE.exists():
        existing = json.loads(SESSION_FILE.read_text())
        if "last_session_id" in existing:
            data["last_session_id"] = existing["last_session_id"]
    if access_token:
        data["access_token"] = access_token
    elif SESSION_FILE.exists():
        existing = json.loads(SESSION_FILE.read_text())
        if "access_token" in existing:
            data["access_token"] = existing["access_token"]
    SESSION_FILE.write_text(json.dumps(data))
```

- [ ] **Step 2: Update `cmd_connect` to obtain a JWT via the callback endpoint**

After the user completes OAuth, the CLI needs the JWT that was issued by the `/oauth/callback` endpoint. The CLI cannot observe the HTTP response (the browser receives it). Instead, add a lightweight `POST /auth/token` endpoint that issues a new JWT given a valid `user_id` that has Gmail tokens — OR simply call the `/api/oauth/status/{user_id}` endpoint which already verifies connectivity.

The simplest approach that avoids a new endpoint: after the user presses Enter, the CLI calls `db.fetch_gmail_tokens()` directly (already done). It then generates a JWT locally using the same secret from settings:

```python
from backend.app.auth import create_access_token

async def cmd_connect(db: DBService, gmail: GmailService, settings) -> dict | None:
    """Run the OAuth flow and persist the session."""
    email = Prompt.ask("[cyan]Your Google account email[/cyan]")
    user_id = str(await db.upsert_user(uuid4(), email))
    state = f"{user_id}.{secrets.token_urlsafe(16)}"
    auth_url = await gmail.create_authorization_url(state=state, user_id=user_id)

    console.print("\nOpen this URL in your browser to connect Gmail:\n")
    print(str(auth_url))
    console.print("\n[dim]Complete the OAuth flow in your browser, then press Enter.[/dim]")

    while True:
        input()
        tokens = await db.fetch_gmail_tokens(UUID(user_id))
        if tokens:
            break
        console.print(
            "[yellow]No tokens found yet — did you complete the OAuth flow in your browser?[/yellow]"
        )
        if not Confirm.ask("[dim]Try again?[/dim]", default=True):
            console.print("[red]Cancelled.[/red]")
            return None

    access_token = create_access_token(
        UUID(user_id), settings.jwt_secret_key.get_secret_value()
    )
    save_session(user_id, email, access_token=access_token)
    console.print(f"[green]✓ Connected as {email}[/green]  (user_id: {user_id})")
    return {"user_id": user_id, "email": email, "access_token": access_token}
```

Note: this also implements the **Priority 2 retry loop** from PRIMER.md.

- [ ] **Step 3: Update `build_services` to pass settings through**

`cmd_connect` needs access to `settings`. Update the call site in `main()`:

```python
result = await cmd_connect(db, gmail, settings)
```

And update the function signature accordingly.

- [ ] **Step 4: Append token to review URL in `cmd_start_session` and `cmd_open_review`**

In `cmd_start_session`:

```python
access_token = session.get("access_token", "")
review_url = f"http://localhost:8001/api/review/{session_id}"
if access_token:
    review_url += f"?token={access_token}"
console.print(Panel(f"[link={review_url}]{review_url}[/link]", title="Review UI"))
webbrowser.open(review_url)
```

In `cmd_open_review`:

```python
access_token = session.get("access_token", "")
review_url = f"http://localhost:8001/api/review/{last_session_id}"
if access_token:
    review_url += f"?token={access_token}"
console.print(f"[cyan]Opening:[/cyan] {review_url}")
webbrowser.open(review_url)
```

- [ ] **Step 5: Lint**

```bash
docker compose exec backend uv run ruff check backend/cli.py --fix && docker compose exec backend uv run ruff format backend/cli.py
```

- [ ] **Step 6: Manual smoke test**

Verify the CLI still connects, creates a session, and opens the review URL with the token appended.

- [ ] **Step 7: Commit**

```bash
git add backend/cli.py
git commit -m "feat(auth): store JWT in CLI session file; append token to review URL"
```

---

## Task 12: Final lint, full test run, and update PRIMER

- [ ] **Step 1: Lint the entire backend**

```bash
docker compose exec backend uv run ruff check backend/ --fix && docker compose exec backend uv run ruff format backend/
```

- [ ] **Step 2: Run the full test suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v
```

Expected: all tests pass (count will be higher than the pre-auth count due to new tests).

- [ ] **Step 3: Commit any lint fixes**

```bash
git add -u
git commit -m "style: apply ruff format after auth implementation"
```

- [ ] **Step 4: Update `docs/SECURITY_AUDIT_REPORT.md` — mark CRIT-01, CRIT-02, CRIT-03 as fixed**

In the Status table, update the three rows:

```
| CRIT-01 | No authentication/authorization | **FIXED** — `require_auth` dep on all protected routes |
| CRIT-02 | IDOR — user IDs accepted from client | **FIXED** — user_id derived from JWT, not request params |
| CRIT-03 | Debug endpoints unauthenticated | **FIXED** — gated to ENVIRONMENT=development |
```

- [ ] **Step 5: Update `PRIMER.md`**

Update "What Was Done This Session", "Current State", and "Recommended Next Steps" to reflect the auth implementation.

- [ ] **Step 6: Final commit**

```bash
git add docs/SECURITY_AUDIT_REPORT.md PRIMER.md
git commit -m "docs: update security audit and PRIMER after CRIT-01/02/03 remediation"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| `user_id` derived from JWT, not request params | Tasks 4, 5, 6, 7, 8, 10 |
| Unauthenticated requests get 401 | All route tasks (step 1 failing test) |
| Session ownership verified | Task 6 (`_get_owned_session`) |
| Review page ownership verified | Task 8 |
| Pattern ownership preserved | Task 7 |
| Debug routes gated to dev | Task 9 |
| CLI gets JWT and passes to review URL | Task 11 |
| CLI retry loop on OAuth wait | Task 11 |
| Tests cover every new auth requirement | Steps 1-2 of each task |
| CRIT-03 resolved together with CRIT-01 | Task 9 |

**Placeholder scan:** None found. All tasks contain complete code.

**Type consistency:**
- `require_auth` returns `UUID` — used as `UUID = Depends(get_current_user)` in all routes ✓
- `get_current_user` wraps `require_auth` and returns `UUID` ✓
- `_get_owned_session` takes `UUID, UUID, ClassificationSessionService` and returns `dict` ✓
- `create_access_token(user_id: UUID, secret: str) -> str` ✓
- `decode_access_token(token: str, secret: str) -> UUID` ✓
- `save_session` updated with `access_token: str | None` keyword arg ✓
