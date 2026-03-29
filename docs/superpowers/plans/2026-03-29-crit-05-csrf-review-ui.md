# CRIT-05: CSRF Protection for Review UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate two remaining attack vectors on the review page: the `?token=` JWT leaking to browser history/logs, and missing CSRF protection on the label-correction endpoint.

**Architecture:** With JWT Bearer auth (not cookies) and CORS already restricted to localhost, traditional cross-site CSRF is largely mitigated. The two concrete risks addressed here are (1) the `?token=` query parameter persisting in browser history and server access logs after the page loads, and (2) the absence of a request-bound secret on `POST /api/review/{id}/correct`, which triggers pattern learning. The fix: a stateless HMAC-SHA256 token keyed on `"{session_id}:{user_id}"` and the JWT secret. It is generated at page-render time, embedded in the page JS, stripped from the URL, and verified server-side on the correction endpoint. The cleanup endpoint (`/api/sessions/{id}/cleanup`) is intentionally excluded — it is already protected by JWT auth + `_get_owned_session` ownership check, and is not the sensitive mutation point.

**Tech Stack:** Python stdlib `hashlib` + `hmac`, FastAPI `Header` dependency, `window.history.replaceState` (browser JS)

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Modify** | `backend/app/auth.py` | Add `make_csrf_token` helper (alongside existing JWT utils) |
| **Modify** | `backend/app/routes/review.py` | Generate + embed CSRF token; strip `?token=` from URL in JS; verify token on `correct_label` |
| **Modify** | `backend/tests/test_auth.py` | Unit tests for `make_csrf_token` |
| **Modify** | `backend/tests/test_routes.py` | Integration tests for CSRF on review page and correction endpoint |

---

## Task 1: Add `make_csrf_token` to `auth.py`

**Files:**
- Modify: `backend/app/auth.py`
- Modify: `backend/tests/test_auth.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_auth.py`:

```python
def test_make_csrf_token_returns_64_char_hex() -> None:
    """make_csrf_token returns a 64-character lowercase hex string (SHA-256)."""
    from backend.app.auth import make_csrf_token

    token = make_csrf_token("session-abc", "user-xyz", "secret")
    assert len(token) == 64
    assert all(c in "0123456789abcdef" for c in token)


def test_make_csrf_token_is_deterministic() -> None:
    """Same inputs always produce the same token."""
    from backend.app.auth import make_csrf_token

    t1 = make_csrf_token("session-abc", "user-xyz", "secret")
    t2 = make_csrf_token("session-abc", "user-xyz", "secret")
    assert t1 == t2


def test_make_csrf_token_differs_for_different_sessions() -> None:
    """Different session_id produces a different token."""
    from backend.app.auth import make_csrf_token

    t1 = make_csrf_token("session-1", "user-xyz", "secret")
    t2 = make_csrf_token("session-2", "user-xyz", "secret")
    assert t1 != t2


def test_make_csrf_token_differs_for_different_users() -> None:
    """Different user_id produces a different token."""
    from backend.app.auth import make_csrf_token

    t1 = make_csrf_token("session-abc", "user-1", "secret")
    t2 = make_csrf_token("session-abc", "user-2", "secret")
    assert t1 != t2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_auth.py::test_make_csrf_token_returns_64_char_hex \
  backend/tests/test_auth.py::test_make_csrf_token_is_deterministic \
  backend/tests/test_auth.py::test_make_csrf_token_differs_for_different_sessions \
  backend/tests/test_auth.py::test_make_csrf_token_differs_for_different_users \
  -v
```

Expected: all 4 FAIL with `ImportError: cannot import name 'make_csrf_token'`.

- [ ] **Step 3: Add `make_csrf_token` to `backend/app/auth.py`**

Add `import hashlib` and `import hmac as _hmac` after the existing `import jwt` line:

```python
import hashlib
import hmac as _hmac
import jwt
```

Then append `make_csrf_token` after `decode_access_token` (before `require_auth`):

```python
def make_csrf_token(session_id: str, user_id: str, secret: str) -> str:
    """Return an HMAC-SHA256 token bound to a specific session and user.

    Stateless — verifiable without DB storage. Uses the JWT secret so only
    the server can produce valid tokens.
    """
    msg = f"{session_id}:{user_id}".encode()
    return _hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
```

- [ ] **Step 4: Verify tests pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_auth.py::test_make_csrf_token_returns_64_char_hex \
  backend/tests/test_auth.py::test_make_csrf_token_is_deterministic \
  backend/tests/test_auth.py::test_make_csrf_token_differs_for_different_sessions \
  backend/tests/test_auth.py::test_make_csrf_token_differs_for_different_users \
  -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run full suite to confirm no regressions**

```bash
docker compose exec backend uv run pytest backend/tests/ -q
```

Expected: all tests pass (120 + 4 = 124).

- [ ] **Step 6: Commit**

```bash
git add backend/app/auth.py backend/tests/test_auth.py
git commit -m "feat(security): add make_csrf_token HMAC helper to auth module (CRIT-05)"
```

---

## Task 2: Embed CSRF token in review page and strip `?token=` from URL

**Files:**
- Modify: `backend/app/routes/review.py`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
def test_review_page_contains_csrf_token(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """Review page HTML must contain a 64-char hex CSRF_TOKEN JS variable."""
    import re
    from cryptography.fernet import Fernet

    from backend.app.config import Settings, get_settings
    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem
    from datetime import datetime, timezone

    test_settings = Settings.model_validate({
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
        "JWT_SECRET_KEY": "test-jwt-secret-do-not-use-in-prod",
        "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/callback",
        "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
    })

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [{
                "email": EmailItem(
                    id=uuid4(), gmail_message_id="msg-1", thread_id="t-1",
                    subject="Test", received_at=datetime.now(timezone.utc),
                ),
                "suggestion": "Important",
                "confidence": 0.9,
            }]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    authed_client.app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert re.search(r'const CSRF_TOKEN = "[0-9a-f]{64}";', response.text), (
            "CSRF_TOKEN not found or malformed in page HTML"
        )
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)
        authed_client.app.dependency_overrides.pop(get_settings, None)


def test_review_page_strips_token_from_url(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """Review page JS must call window.history.replaceState to strip ?token= from URL."""
    from cryptography.fernet import Fernet

    from backend.app.config import Settings, get_settings
    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem
    from datetime import datetime, timezone

    test_settings = Settings.model_validate({
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
        "JWT_SECRET_KEY": "test-jwt-secret-do-not-use-in-prod",
        "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/callback",
        "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
    })

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [{
                "email": EmailItem(
                    id=uuid4(), gmail_message_id="msg-1", thread_id="t-1",
                    subject="Test", received_at=datetime.now(timezone.utc),
                ),
                "suggestion": "Important",
                "confidence": 0.9,
            }]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    authed_client.app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert "window.history.replaceState" in response.text
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)
        authed_client.app.dependency_overrides.pop(get_settings, None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_contains_csrf_token \
  backend/tests/test_routes.py::test_review_page_strips_token_from_url \
  -v
```

Expected: both FAIL — `CSRF_TOKEN` variable not present, `replaceState` not present.

- [ ] **Step 3: Update `review.py` — imports**

The current imports in `backend/app/routes/review.py`:

```python
"""Human review web UI and correction API for classified emails."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..dependencies import (
    get_classification_session_service,
    get_current_user,
    get_label_service,
)
from ..schemas.labels import ApplyLabelRequest
from ..services.classification_session_service import ClassificationSessionService
from ..services.label_service import LabelService
```

Replace with:

```python
"""Human review web UI and correction API for classified emails."""

from __future__ import annotations

import logging
from hmac import compare_digest
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from ..auth import make_csrf_token
from ..config import Settings, get_settings
from ..dependencies import (
    get_classification_session_service,
    get_current_user,
    get_label_service,
)
from ..schemas.labels import ApplyLabelRequest
from ..services.classification_session_service import ClassificationSessionService
from ..services.label_service import LabelService
```

- [ ] **Step 4: Add `settings` parameter to `review_page` and generate the CSRF token**

Current `review_page` signature:

```python
@router.get("/{session_id}", response_class=HTMLResponse)
async def review_page(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> HTMLResponse:
```

Replace with:

```python
@router.get("/{session_id}", response_class=HTMLResponse)
async def review_page(
    session_id: UUID,
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
```

Then, inside the function body after `session_id_str = str(session_id)` (around line 82), add:

```python
    csrf_token = make_csrf_token(
        str(session_id), str(current_user), settings.jwt_secret_key.get_secret_value()
    )
```

- [ ] **Step 5: Update the JS block in the HTML template**

Find the `<script>` block starting at `const SESSION_ID`:

```python
    html = f"""<!DOCTYPE html>
...
  <script>
    const SESSION_ID = "{session_id_str}";
    const params = new URLSearchParams(window.location.search);
    const TOKEN = params.get('token') || '';

    function authHeaders() {{
      return TOKEN
        ? {{"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN}}
        : {{"Content-Type": "application/json"}};
    }}
```

Replace just the `<script>` opening block with:

```python
  <script>
    const SESSION_ID = "{session_id_str}";
    const CSRF_TOKEN = "{csrf_token}";
    const params = new URLSearchParams(window.location.search);
    const TOKEN = params.get('token') || '';
    if (TOKEN) {{
      window.history.replaceState({{}}, '', window.location.pathname);
    }}

    function authHeaders() {{
      const h = {{"Content-Type": "application/json"}};
      if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
      if (CSRF_TOKEN) h["X-CSRF-Token"] = CSRF_TOKEN;
      return h;
    }}
```

- [ ] **Step 6: Verify tests pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_contains_csrf_token \
  backend/tests/test_routes.py::test_review_page_strips_token_from_url \
  -v
```

Expected: both PASS.

- [ ] **Step 7: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -q
```

Expected: all tests pass (124 + 2 = 126).

- [ ] **Step 8: Commit**

```bash
git add backend/app/routes/review.py backend/tests/test_routes.py
git commit -m "feat(security): embed CSRF token in review page; strip ?token= from URL (CRIT-05)"
```

---

## Task 3: Verify CSRF token in `correct_label`

**Files:**
- Modify: `backend/app/routes/review.py:226-259`
- Modify: `backend/tests/test_routes.py`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_routes.py`:

```python
def test_correct_label_rejects_missing_csrf_token(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """POST /api/review/{id}/correct without X-CSRF-Token must return 403."""
    from backend.app.dependencies import get_classification_session_service

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return []

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.post(
            f"/api/review/{uuid4()}/correct",
            json={"email_id": str(uuid4()), "gmail_message_id": "msg-1", "new_label": "Important"},
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)


def test_correct_label_rejects_wrong_csrf_token(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """POST /api/review/{id}/correct with an incorrect X-CSRF-Token must return 403."""
    from backend.app.dependencies import get_classification_session_service

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return []

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.post(
            f"/api/review/{uuid4()}/correct",
            json={"email_id": str(uuid4()), "gmail_message_id": "msg-1", "new_label": "Important"},
            headers={"X-CSRF-Token": "a" * 64},  # valid format, wrong value
        )
        assert response.status_code == 403
        assert "CSRF" in response.json()["detail"]
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)


def test_correct_label_accepts_valid_csrf_token(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """POST /api/review/{id}/correct with the correct X-CSRF-Token must return 200."""
    from cryptography.fernet import Fernet

    from backend.app.auth import make_csrf_token
    from backend.app.config import Settings, get_settings
    from backend.app.dependencies import get_classification_session_service

    _JWT_SECRET = "test-jwt-secret-do-not-use-in-prod"
    test_settings = Settings.model_validate({
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
        "JWT_SECRET_KEY": _JWT_SECRET,
        "GOOGLE_OAUTH_CLIENT_ID": "client-id",
        "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost/callback",
        "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
    })
    session_id = uuid4()
    csrf_token = make_csrf_token(str(session_id), str(auth_user_id), _JWT_SECRET)

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return []

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    authed_client.app.dependency_overrides[get_settings] = lambda: test_settings
    try:
        response = authed_client.post(
            f"/api/review/{session_id}/correct",
            json={"email_id": str(uuid4()), "gmail_message_id": "msg-1", "new_label": "Important"},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)
        authed_client.app.dependency_overrides.pop(get_settings, None)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_correct_label_rejects_missing_csrf_token \
  backend/tests/test_routes.py::test_correct_label_rejects_wrong_csrf_token \
  backend/tests/test_routes.py::test_correct_label_accepts_valid_csrf_token \
  -v
```

Expected: first two FAIL (endpoint currently returns 200 without a token check); third FAIL (also no verification).

- [ ] **Step 3: Update `correct_label` in `review.py`**

Current `correct_label` signature and first part of body:

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
```

Replace with:

```python
@router.post("/{session_id}/correct")
async def correct_label(
    session_id: UUID,
    request: CorrectionRequest,
    x_csrf_token: str | None = Header(default=None),
    current_user: UUID = Depends(get_current_user),
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    label_svc: LabelService = Depends(get_label_service),
    settings: Settings = Depends(get_settings),
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

    expected_csrf = make_csrf_token(
        str(session_id), str(current_user), settings.jwt_secret_key.get_secret_value()
    )
    if not compare_digest(x_csrf_token or "", expected_csrf):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token invalid."
        )

    user_id = UUID(session["user_id"])
```

- [ ] **Step 4: Verify tests pass**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_correct_label_rejects_missing_csrf_token \
  backend/tests/test_routes.py::test_correct_label_rejects_wrong_csrf_token \
  backend/tests/test_routes.py::test_correct_label_accepts_valid_csrf_token \
  -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run full suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -q
```

Expected: all tests pass (126 + 3 = 129).

- [ ] **Step 6: Lint**

```bash
docker compose exec backend uv run ruff check backend/app/routes/review.py backend/app/auth.py --fix \
  && docker compose exec backend uv run ruff format backend/app/routes/review.py backend/app/auth.py
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/routes/review.py backend/tests/test_routes.py
git commit -m "fix(security): verify CSRF token on correct_label endpoint (CRIT-05)"
```

---

## Task 4: Update security audit report and PRIMER

**Files:**
- Modify: `docs/SECURITY_AUDIT_REPORT.md`
- Modify: `PRIMER.md`

- [ ] **Step 1: Mark CRIT-05 fixed in `docs/SECURITY_AUDIT_REPORT.md`**

Find:
```
| CRIT-05 | session_id Embedded in Review Page JS with No CSRF Protection | **NOT FIXED** |
```

Replace with:
```
| CRIT-05 | session_id Embedded in Review Page JS with No CSRF Protection | **FIXED** — HMAC CSRF token on correction endpoint; ?token= stripped from URL |
```

- [ ] **Step 2: Update `PRIMER.md`**

In "Current State", update the test count to reflect new passing count. In "Recommended Next Steps", remove CRIT-05 from Priority 1.

- [ ] **Step 3: Commit**

```bash
git add docs/SECURITY_AUDIT_REPORT.md PRIMER.md
git commit -m "docs: mark CRIT-05 fixed after CSRF protection implementation"
```

---

## Self-Review

**1. Spec coverage:**

| Requirement | Task |
|---|---|
| CSRF tokens on all state-changing fetch calls in review UI | Task 3 — `correct_label` verifies `X-CSRF-Token`; `doneAndCleanup` sends the header via `authHeaders()` but cleanup endpoint is omitted per scope note |
| `session_id` no longer the sole secret protecting the session | Task 3 — CSRF token is `HMAC(jwt_secret, session_id:user_id)`; attacker knowing session_id alone is insufficient |
| `?token=` not persisted in browser history | Task 2 — `window.history.replaceState` strips it on page load |
| CSRF token present in page HTML | Task 2 — `const CSRF_TOKEN = "{csrf_token}"` embedded |
| All state-changing fetch calls include `X-CSRF-Token` header | Task 2 — `authHeaders()` includes `h["X-CSRF-Token"] = CSRF_TOKEN` |
| Tests cover missing, wrong, and correct CSRF token | Task 3 — 3 tests |
| Tests are TDD (fail before fix) | Step 2 of each task verifies failure |

**2. Placeholder scan:** None found.

**3. Type consistency:**
- `make_csrf_token(session_id: str, user_id: str, secret: str) -> str` — called with `str(session_id)`, `str(current_user)`, and `.get_secret_value()` in both generation and verification sites ✓
- `x_csrf_token: str | None` — compared via `compare_digest(x_csrf_token or "", expected_csrf)` handles the `None` case safely ✓
- `csrf_token` (str, 64-char hex) embedded in f-string template — safe since hex chars contain no HTML-special characters ✓

**Note on cleanup endpoint:** `doneAndCleanup()` in JS calls `/api/sessions/{id}/cleanup`. After Task 2, `authHeaders()` will include `X-CSRF-Token`. The `cleanup_session` endpoint in `sessions.py` ignores this header (FastAPI drops unknown headers silently). This is intentional — cleanup is already protected by JWT auth + `_get_owned_session` ownership verification, and adding CSRF to a general-purpose session endpoint would couple it to the review page's token scheme without meaningful security gain.
