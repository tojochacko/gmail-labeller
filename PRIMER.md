# PRIMER

Session handoff document. Updated at the end of each session.

---

## What Was Done This Session

### HIGH-01: OAuth State CSRF Protection (complete)

Fixed the OAuth CSRF vulnerability where the `state` parameter was generated but never verified server-side, allowing an attacker to craft a callback linking an arbitrary code to a victim's account.

- **`backend/app/db/models.py`**: Added `OAuthState` model (`oauth_states` table — `state` PK, `created_at`)
- **`backend/alembic/versions/a1b2c3d4e5f6_add_oauth_state_table.py`**: Migration for new table
- **`backend/app/services/db_service.py`**: Added `store_oauth_state` and `verify_and_consume_oauth_state` (10-min TTL, atomic delete on both valid and expired paths)
- **`backend/app/routes/oauth.py`**: `/start` stores state after `upsert_user`; `/callback` verifies+consumes state before token exchange — returns 400 on invalid/expired/replayed state
- **`backend/tests/test_db_service.py`**: 3 new DB-layer tests (happy path, unknown state, expired state)
- **`backend/tests/test_routes.py`**: Updated callback test to pre-seed state; added 3 rejection tests (unknown, replayed, invalid format)
- **`backend/tests/conftest.py`**: `FakeDBService` updated with `store_oauth_state` / `verify_and_consume_oauth_state`

### HIGH-03: Already Fixed (confirmed)

Audit of `backend/app/routes/sessions.py` confirmed that all four session endpoints (`get_session`, `run_session`, `get_session_emails`, `cleanup_session`) already call `_get_owned_session`. No new work needed.

---

## Prior Session Work

### 1. Security Audit (re-run)
Re-ran a full security audit after substantial codebase changes. New report in `docs/SECURITY_AUDIT_REPORT.md` covers 25 findings (12 prior + 13 new), rated CRIT/HIGH/MED/LOW.

### 2. JWT Authentication — CRIT-01, CRIT-02, CRIT-03, HIGH-02 (complete)
Full JWT auth implementation across all FastAPI endpoints. Key changes:

- **`backend/app/auth.py`** (new): `create_access_token`, `decode_access_token`, `require_auth` FastAPI dependency (reads `Authorization: Bearer` header or `?token=` query param)
- **`backend/app/config.py`**: added `JWT_SECRET_KEY: SecretStr` and `ENVIRONMENT: str` (default `"production"`)
- **`backend/app/dependencies.py`**: added `get_current_user` dependency (wraps `require_auth`; overridable in tests via `dependency_overrides`)
- **`backend/app/routes/oauth.py`**: `/callback` now issues a JWT and returns it in the response; `/status/{user_id}` now requires auth and ownership check
- **`backend/app/routes/emails.py`**: `user_id` from JWT, not query param
- **`backend/app/routes/labels.py`**: `user_id` overridden from JWT
- **`backend/app/routes/sessions.py`**: all 5 endpoints protected; `_get_owned_session` helper enforces 404/403 ownership checks
- **`backend/app/routes/patterns.py`**: all 6 endpoints protected
- **`backend/app/routes/review.py`**: auth on page + correct endpoints; JS reads `?token=` from URL and attaches as `Authorization: Bearer` on all fetch calls
- **`backend/app/routes/agent.py`**: both `/api/runs` and `/api/runs/{run_id}` protected; `user_id` overridden from JWT
- **`backend/app/routes/debug.py`**: `_require_dev` dependency — returns 403 unless `ENVIRONMENT=development`; design decision (runtime gating over conditional registration) documented in `routes/__init__.py`
- **`backend/cli.py`**: generates JWT locally after OAuth; persists it in `~/.gmail-labeler/session.json` (chmod 0o600); appends `?token=` to review URLs (token hidden from terminal display); retry loop if user presses Enter before OAuth completes

### 3. New Tests Added
- `backend/tests/test_auth.py`: JWT roundtrip, tampered/expired/malformed token 401 tests
- `backend/tests/test_routes.py`: 401/403 tests for every protected route; happy-path tests; `_require_dev` unit tests for both dev and production modes; agent run auth tests

---

## Current State

- **Branch:** `main`
- **Tests:** 140/140 passing in Docker container
- **Docker:** `autogen-test-backend-1` running (`docker compose up -d` from project root to start)
- **OAuth:** End-to-end flow working with JWT; CLI stores token and appends to review URL
- **Auth:** All routes protected — unauthenticated requests return 401; cross-user access returns 403
- **Security fixes:** CRIT-01, CRIT-02, CRIT-03, HIGH-01, HIGH-02 resolved. HIGH-03 was already fixed (all session endpoints use `_get_owned_session`). See `docs/SECURITY_AUDIT_REPORT.md` for remaining open findings.
- **Registered redirect URI:** `http://localhost:8001/api/oauth/callback` in Google Cloud Console

---

## Recommended Next Steps

### Priority 1 — Remaining HIGH findings (from `docs/SECURITY_AUDIT_REPORT.md`)

**Next session: create implementation plans for remaining HIGH items.**

- **HIGH-04**: Email snippet logged and sent to LLM unredacted — full subject+sender+snippet logged at INFO before Presidio, stored in DB unredacted at ingestion; Presidio absence silently passes through to LLM
- **HIGH-05**: Prompt injection via learned patterns — extracted email-subject patterns injected verbatim into LLM prompts, unbounded growth

### Priority 2 — Add tests for the two job alert fixes (from prior session)
- `test_job_alert_detector.py`: add cases for display-name format emails e.g. `"LinkedIn <jobs-listings@linkedin.com>"`
- `test_agent_service.py` or mock test: verify `is_job_alert` appears in OpenAI system prompt

### Priority 3 — Config: add `JWT_SECRET_KEY` to `config/env.example`
The new required env var `JWT_SECRET_KEY` should be documented in `config/env.example` with a generation note.

---

## Key Commands

```bash
# Start container
docker compose up -d

# Start FastAPI server (required for OAuth callback and API access)
docker compose exec backend uv run uvicorn backend.app.main:create_app --factory --host 0.0.0.0 --port 8000

# Run CLI (stop uvicorn first if OAuth is needed, or run alongside for batch classification)
docker compose exec backend uv run python -m backend.cli

# Run tests
docker compose exec backend uv run pytest backend/tests/ -v

# Lint
docker compose exec backend uv run ruff check backend/ --fix && docker compose exec backend uv run ruff format backend/

# Stop container
docker compose down
```

## Implementation Plans
Saved in `docs/superpowers/plans/`:
- `2026-03-27-gmail-api-direct.md` — completed ✅
- `2026-03-27-job-alert-labeling.md` — completed ✅
- `2026-03-29-crit-01-jwt-auth.md` — completed ✅
- `2026-03-29-crit-04-xss-review-ui.md` — completed ✅
- `2026-03-29-crit-05-csrf-review-ui.md` — completed ✅
- `2026-03-30-high-01-oauth-state-verification.md` — completed ✅
