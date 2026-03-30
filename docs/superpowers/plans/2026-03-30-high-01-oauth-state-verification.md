# HIGH-01: OAuth State Server-Side Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store the OAuth `state` parameter server-side at `/oauth/start` and verify + consume it at `/oauth/callback` to prevent CSRF attacks that link arbitrary authorization codes to victim accounts.

**Architecture:** Add a short-lived `OAuthState` table (state string PK, `created_at` ISO-8601 string). On `/start`, persist the state. On `/callback`, look it up, reject if missing or older than 10 minutes, then delete it to prevent replay. The `FakeDBService` in `conftest.py` gains the same two methods so existing route tests keep working.

**Tech Stack:** SQLAlchemy async ORM, Alembic migrations, FastAPI, pytest, aiosqlite (in-memory for tests)

> **Note on HIGH-03:** HIGH-03 (no ownership check on session read/run/emails) is **already fixed** — `sessions.py` calls `_get_owned_session` on all four session endpoints. No work needed.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/db/models.py` | Add `OAuthState` ORM model |
| Create | `backend/alembic/versions/<rev>_add_oauth_state_table.py` | DB migration for new table |
| Modify | `backend/app/services/db_service.py` | Add `store_oauth_state` + `verify_and_consume_oauth_state` |
| Modify | `backend/app/routes/oauth.py` | Store state in `/start`; verify in `/callback` |
| Modify | `backend/tests/conftest.py` | Add state dict + two methods to `FakeDBService` |
| Modify | `backend/tests/test_routes.py` | Update callback test; add 3 new rejection tests |
| Modify | `backend/tests/test_db_service.py` | Add 3 DB-level tests for state lifecycle |

---

### Task 1: Add `OAuthState` ORM model

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Write the failing import test**

In `backend/tests/test_db_service.py`, add at the top of the file (after the existing imports):

```python
from backend.app.db.models import OAuthState  # noqa: F401 — import-only check
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker compose exec backend uv run pytest backend/tests/test_db_service.py -k "not test_" -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'OAuthState'`

- [ ] **Step 3: Add `OAuthState` to `backend/app/db/models.py`**

Open `backend/app/db/models.py`. After the `ClassificationSession` class (end of file), append:

```python
class OAuthState(Base):
    __tablename__ = "oauth_states"

    state = Column(String(100), primary_key=True)
    created_at = Column(String(50), nullable=False)
```

- [ ] **Step 4: Verify the import succeeds**

```bash
docker compose exec backend uv run python -c "from backend.app.db.models import OAuthState; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/models.py
git commit -m "feat(auth): add OAuthState ORM model for server-side state verification"
```

---

### Task 2: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/<rev>_add_oauth_state_table.py`

- [ ] **Step 1: Generate migration**

```bash
docker compose exec backend uv run alembic revision --autogenerate -m "add_oauth_state_table"
```

Expected output: `Generating .../versions/<hash>_add_oauth_state_table.py ... done`

Note the generated filename — it will be in `backend/alembic/versions/`.

- [ ] **Step 2: Inspect the generated migration**

Open `backend/alembic/versions/<hash>_add_oauth_state_table.py` and confirm the `upgrade()` function creates the `oauth_states` table:

```python
def upgrade() -> None:
    op.create_table('oauth_states',
    sa.Column('state', sa.String(length=100), nullable=False),
    sa.Column('created_at', sa.String(length=50), nullable=False),
    sa.PrimaryKeyConstraint('state')
    )

def downgrade() -> None:
    op.drop_table('oauth_states')
```

If the auto-generated output differs in column types but is logically equivalent, leave it as-is. Only edit if a column is missing or wrong.

- [ ] **Step 3: Apply migration to the dev DB**

```bash
docker compose exec backend uv run alembic upgrade head
```

Expected: `Running upgrade 5b2aaeb07965 -> <new_rev>, add_oauth_state_table`

- [ ] **Step 4: Verify table exists**

```bash
docker compose exec backend uv run python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

async def check():
    engine = create_async_engine('sqlite+aiosqlite:///./backend.db')
    async with engine.connect() as conn:
        result = await conn.execute(text(\"SELECT name FROM sqlite_master WHERE type='table' AND name='oauth_states'\"))
        print(result.scalar())

asyncio.run(check())
"
```

Expected: `oauth_states`

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/
git commit -m "chore(db): migration to add oauth_states table"
```

---

### Task 3: Add `store_oauth_state` and `verify_and_consume_oauth_state` to `DBService`

**Files:**
- Modify: `backend/app/services/db_service.py`
- Modify: `backend/tests/test_db_service.py`

- [ ] **Step 1: Write the failing tests**

In `backend/tests/test_db_service.py`, add after the existing imports (add `timedelta` to datetime import):

```python
from datetime import timedelta
```

Then add these three tests at the end of the file:

```python
@pytest.mark.asyncio
async def test_store_and_consume_oauth_state(db_service: DBService) -> None:
    """A state stored by store_oauth_state should be consumed once."""
    state = "user-id.randomtoken"
    await db_service.store_oauth_state(state)
    result = await db_service.verify_and_consume_oauth_state(state)
    assert result is True


@pytest.mark.asyncio
async def test_consume_unknown_state_returns_false(db_service: DBService) -> None:
    """verify_and_consume_oauth_state returns False for an unrecognised state."""
    result = await db_service.verify_and_consume_oauth_state("nonexistent.state")
    assert result is False


@pytest.mark.asyncio
async def test_consume_expired_state_returns_false(db_service: DBService) -> None:
    """verify_and_consume_oauth_state returns False when the state is older than 10 minutes."""
    from backend.app.db.models import OAuthState
    from sqlalchemy import insert

    old_ts = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat()
    state = "user-id.expiredtoken"
    async with db_service.session_factory() as session:
        await session.execute(
            insert(OAuthState).values(state=state, created_at=old_ts)
        )
        await session.commit()
    result = await db_service.verify_and_consume_oauth_state(state)
    assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest backend/tests/test_db_service.py -k "oauth_state" -v
```

Expected: `AttributeError: 'DBService' object has no attribute 'store_oauth_state'`

- [ ] **Step 3: Add `store_oauth_state` to `db_service.py`**

In `backend/app/services/db_service.py`:

1. Add `OAuthState` to the models import line:
```python
from ..db.models import AgentRun, Email, GmailToken, LabelPattern, OAuthState, User
```

2. Add `timedelta` to the datetime import:
```python
from datetime import datetime, timedelta, timezone
```

3. After the `fetch_gmail_tokens` method block, add a new section:

```python
    # ------------------------------------------------------------------
    # OAuth state (CSRF protection)
    # ------------------------------------------------------------------

    async def store_oauth_state(self, state: str) -> None:
        """Persist an OAuth state string with a creation timestamp."""
        created_at = datetime.now(timezone.utc).isoformat()
        async with self._session_factory() as session:
            session.add(OAuthState(state=state, created_at=created_at))
            await session.commit()

    async def verify_and_consume_oauth_state(self, state: str, ttl_minutes: int = 10) -> bool:
        """Return True and delete the state if it exists and is not expired; False otherwise."""
        async with self._session_factory() as session:
            obj = await session.get(OAuthState, state)
            if obj is None:
                return False
            created = datetime.fromisoformat(obj.created_at)
            if datetime.now(timezone.utc) - created > timedelta(minutes=ttl_minutes):
                await session.delete(obj)
                await session.commit()
                return False
            await session.delete(obj)
            await session.commit()
            return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose exec backend uv run pytest backend/tests/test_db_service.py -k "oauth_state" -v
```

Expected: 3 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/db_service.py backend/tests/test_db_service.py
git commit -m "feat(auth): add store/verify_and_consume_oauth_state to DBService"
```

---

### Task 4: Enforce state verification in OAuth routes

**Files:**
- Modify: `backend/app/routes/oauth.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write the failing route tests**

In `backend/tests/test_routes.py`, replace the existing `test_oauth_callback_stores_tokens_and_returns_token` test and add three new ones:

```python
def test_oauth_callback_stores_tokens_and_returns_token(
    client: TestClient, fake_supabase
) -> None:
    """Callback succeeds when the state matches a pre-stored value."""
    user_id = uuid4()
    state = f"{user_id}.somesecret"
    # Pre-seed the state so the server-side check passes
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        fake_supabase.store_oauth_state(state)
    )
    response = client.get(f"/api/oauth/callback?code=auth-code&state={state}")
    assert response.status_code == 200
    data = response.json()
    assert data["connected"] is True
    assert "access_token" in data
    assert isinstance(data["access_token"], str) and len(data["access_token"]) > 20
    assert user_id in fake_supabase.tokens


def test_oauth_callback_rejects_unknown_state(client: TestClient) -> None:
    """Callback returns 400 when the state was never stored server-side."""
    user_id = uuid4()
    state = f"{user_id}.unknowntoken"
    response = client.get(f"/api/oauth/callback?code=auth-code&state={state}")
    assert response.status_code == 400
    assert "state" in response.json()["detail"].lower()


def test_oauth_callback_rejects_replayed_state(
    client: TestClient, fake_supabase
) -> None:
    """Callback returns 400 on second use of the same state (replay prevention)."""
    user_id = uuid4()
    state = f"{user_id}.onceonly"
    import asyncio
    asyncio.get_event_loop().run_until_complete(
        fake_supabase.store_oauth_state(state)
    )
    # First call — should succeed
    r1 = client.get(f"/api/oauth/callback?code=auth-code&state={state}")
    assert r1.status_code == 200
    # Second call — state consumed, should fail
    r2 = client.get(f"/api/oauth/callback?code=auth-code&state={state}")
    assert r2.status_code == 400


def test_oauth_callback_rejects_invalid_state_format(client: TestClient) -> None:
    """Callback returns 400 when the state string has no user_id prefix."""
    response = client.get("/api/oauth/callback?code=auth-code&state=notauuid")
    assert response.status_code == 400
```

- [ ] **Step 2: Update `FakeDBService` in `conftest.py`**

In `backend/tests/conftest.py`, update the `FakeDBService` class to add state storage:

```python
class FakeDBService:
    def __init__(self) -> None:
        self.users: dict[UUID, str] = {}
        self.tokens: dict[UUID, GmailTokens] = {}
        self.emails: dict[UUID, EmailItem] = {}
        self.agent_runs: dict[UUID, AgentRunStatusResponse] = {}
        self._oauth_states: set[str] = set()

    async def upsert_user(self, user_id: UUID, email: str) -> None:
        self.users[user_id] = email

    async def store_gmail_tokens(self, user_id: UUID, tokens: GmailTokens) -> None:
        self.tokens[user_id] = tokens

    async def fetch_gmail_tokens(self, user_id: UUID) -> GmailTokens | None:
        return self.tokens.get(user_id)

    async def store_oauth_state(self, state: str) -> None:
        self._oauth_states.add(state)

    async def verify_and_consume_oauth_state(self, state: str, ttl_minutes: int = 10) -> bool:
        if state in self._oauth_states:
            self._oauth_states.discard(state)
            return True
        return False

    async def upsert_email(self, user_id: UUID, payload: EmailItem) -> None:
        self.emails[payload.id] = payload

    async def record_agent_run(
        self,
        run_id: UUID,
        user_id: UUID,
        email_id: UUID,
        status: str,
        result_payload: dict | None = None,
        error_message: str | None = None,
        batch_run_id: UUID | None = None,
    ) -> None:
        self.agent_runs[run_id] = AgentRunStatusResponse(
            run_id=run_id,
            status=status,
            result_payload=result_payload,
            updated_at=datetime.now(timezone.utc),
            error_message=error_message,
        )

    async def fetch_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        return self.agent_runs.get(run_id)
```

- [ ] **Step 3: Run the new tests to confirm they fail**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py -k "oauth_callback" -v
```

Expected: `test_oauth_callback_rejects_unknown_state` PASSED (route doesn't check yet — it will accidentally pass on the invalid-format test but fail the unknown-state check once route is updated). The important baseline is recorded.

Actually, expect `test_oauth_callback_stores_tokens_and_returns_token` to FAIL because `FakeDBService` now has `verify_and_consume_oauth_state` but the route doesn't call it yet, so the pre-stored state is ignored. The test pre-stores it but route succeeds without checking — the happy-path test still passes. The `test_oauth_callback_rejects_unknown_state` will PASS (route returns 200, not 400) — confirming it's not yet enforced.

Run to confirm current state:
```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py -k "oauth_callback" -v 2>&1 | tail -20
```

- [ ] **Step 4: Update `oauth.py` to store state on `/start` and verify on `/callback`**

In `backend/app/routes/oauth.py`:

Replace the entire file content with:

```python
"""OAuth endpoints."""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth import create_access_token
from ..config import Settings, get_settings
from ..dependencies import get_db_service, get_gmail_service, get_current_user
from ..schemas.oauth import (
    OAuthCallbackResponse,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthStatusResponse,
)
from ..services.db_service import DBService
from ..services.gmail_toolkit import GmailService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/start", response_model=OAuthStartResponse, status_code=status.HTTP_200_OK)
async def start_oauth_flow(
    payload: OAuthStartRequest,
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: DBService = Depends(get_db_service),
) -> OAuthStartResponse:
    """Kick off Gmail OAuth by returning an authorization URL."""
    state = f"{payload.user_id}.{secrets.token_urlsafe(16)}"
    await supabase.upsert_user(payload.user_id, payload.email)
    await supabase.store_oauth_state(state)
    authorization_url = await gmail_service.create_authorization_url(
        state=state, user_id=str(payload.user_id)
    )
    logger.info("Generated Gmail OAuth URL for user {}", payload.user_id)
    return OAuthStartResponse(authorization_url=authorization_url, state=state)  # type: ignore[arg-type]


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
    valid = await supabase.verify_and_consume_oauth_state(state)
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired OAuth state parameter.",
        )
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

- [ ] **Step 5: Run all OAuth callback tests**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py -k "oauth" -v
```

Expected: all 7 OAuth-related tests PASS:
- `test_oauth_start_returns_authorization_url`
- `test_oauth_callback_stores_tokens_and_returns_token`
- `test_oauth_callback_rejects_unknown_state`
- `test_oauth_callback_rejects_replayed_state`
- `test_oauth_callback_rejects_invalid_state_format`
- `test_oauth_status_requires_auth`
- `test_oauth_status_forbidden_for_other_user`
- `test_oauth_status_returns_200_for_own_user`

- [ ] **Step 6: Run the full test suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -v 2>&1 | tail -20
```

Expected: All tests PASS (count should be prior count + 3 new tests).

- [ ] **Step 7: Lint**

```bash
docker compose exec backend uv run ruff check backend/ --fix && docker compose exec backend uv run ruff format backend/
```

Expected: No errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/oauth.py backend/tests/conftest.py backend/tests/test_routes.py
git commit -m "fix(security): verify OAuth state server-side to prevent CSRF (HIGH-01)"
```

---

### Task 5: Mark HIGH-01 fixed in security audit and update docs

**Files:**
- Modify: `docs/SECURITY_AUDIT_REPORT.md`
- Modify: `PRIMER.md`

- [ ] **Step 1: Update the status table in `docs/SECURITY_AUDIT_REPORT.md`**

Find the line:
```
| HIGH-01 | OAuth state not verified server-side | **NOT FIXED** |
```

Replace with:
```
| HIGH-01 | OAuth state not verified server-side | **FIXED** — state stored on `/start`, verified+consumed on `/callback`; expired/replayed states return 400 |
```

- [ ] **Step 2: Update `PRIMER.md`**

In `PRIMER.md`, update the "Recommended Next Steps" section to remove HIGH-01 from the open list and note it as resolved:

Find and remove:
```
- **HIGH-01**: OAuth state not verified server-side — attacker can link arbitrary token to victim's account via crafted callback (CSRF in OAuth flow)
```

Add to the "Current State" section:
```
- **HIGH-01**: Fixed — OAuth state stored server-side, verified and consumed on callback.
- **HIGH-03**: Already fixed in previous session — `_get_owned_session` enforces ownership on all session endpoints.
```

Also update the Implementation Plans list in `PRIMER.md`:
```
- `2026-03-30-high-01-oauth-state-verification.md` — completed ✅
```

- [ ] **Step 3: Commit**

```bash
git add docs/SECURITY_AUDIT_REPORT.md PRIMER.md
git commit -m "docs: mark HIGH-01 fixed and HIGH-03 already resolved in security audit"
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] HIGH-01: state stored on `/start` → Task 4 Step 4
- [x] HIGH-01: state verified + consumed on `/callback` → Task 4 Step 4
- [x] HIGH-01: expired state rejected → Task 3 (DB layer), Task 4 tests
- [x] HIGH-01: replayed state rejected (consumed on first use) → Task 4 tests
- [x] HIGH-03: noted as already fixed → Plan header note + Task 5

**No placeholders:** All tasks contain complete code.

**Type consistency:** `store_oauth_state(state: str) -> None` and `verify_and_consume_oauth_state(state: str, ttl_minutes: int = 10) -> bool` are used consistently across `db_service.py`, `FakeDBService`, and `oauth.py`.
