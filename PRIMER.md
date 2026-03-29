# PRIMER

Session handoff document. Updated at the end of each session.

---

## What Was Done This Session

### 1. End-to-End OAuth Flow Fixed
Resolved a series of issues blocking the Gmail OAuth flow in local Docker development:
- `docker-compose.yml`: fixed `DATABASE_URL` to `sqlite+aiosqlite://` (required by async SQLAlchemy); added port mapping `8001:8000`
- `backend/app/db/engine.py`: removed `check_same_thread=False` (invalid for aiosqlite)
- `backend/app/routes/oauth.py`: changed `/callback` from POST to GET; encodes `user_id` into the `state` param so Google's redirect carries the identity back
- `backend/app/services/gmail_toolkit.py`: disabled PKCE (`autogenerate_code_verifier=False`); removed `include_granted_scopes` which caused Google 400 errors
- `backend/app/services/db_service.py`: `upsert_user` now looks up by email first and returns the authoritative UUID (fixes UNIQUE constraint crash on reconnect); added `delete_gmail_tokens` for disconnect support

### 2. CLI Migrated from SupabaseService to DBService
`backend/cli.py` was referencing the deleted `SupabaseService`. Full migration:
- Replaced all `SupabaseService` references with `DBService` via `make_engine` + `make_session_factory`
- Removed embedded OAuth callback HTTP server (was conflicting with Docker port mapping)
- CLI now prints the auth URL, user completes OAuth in browser (FastAPI handles callback), then presses Enter — CLI checks DB for tokens
- Fixed state/user_id ordering bug: `state` was built before `upsert_user` returned the authoritative UUID, so tokens were stored under the wrong user
- Added "Disconnect Gmail" option (menu option 3) — deletes tokens and clears local session file
- Updated all review URLs from `localhost:8000` to `localhost:8001`

### 3. Job Alert Detection Bugs Fixed
Two bugs found via live log analysis that caused a LinkedIn job alert email to not be tagged:
- **`job_alert_detector.py`**: domain regex `r"@([\w.\-]+)$"` failed on display-name format `"LinkedIn <jobs-listings@linkedin.com>"` because of the trailing `>`. Fixed by stripping `<...>` wrapping before the regex
- **`agent_service.py`**: OpenAI system prompt only listed 3 response fields, causing the LLM to omit `is_job_alert`. Fixed by adding `is_job_alert` to the system prompt with explicit instructions; also raised `max_tokens` from 150 → 200 to prevent truncation

---

## Current State

- **Branch:** `main`
- **Tests:** 96/96 passing in Docker container (note: new fixes in `job_alert_detector.py` and `agent_service.py` are not yet covered by tests)
- **Docker:** `autogen-test-backend-1` running (`docker compose up -d` from project root to start)
- **OAuth:** End-to-end flow working — tested via both FastAPI endpoints and CLI
- **Registered redirect URI:** `http://localhost:8001/api/oauth/callback` in Google Cloud Console

---

## Recommended Next Steps

### Priority 1 — Add tests for the two job alert fixes
- `test_job_alert_detector.py`: add cases for display-name format emails e.g. `"LinkedIn <jobs-listings@linkedin.com>"`
- `test_agent_service.py` or mock test: verify `is_job_alert` appears in OpenAI system prompt

### Priority 2 — CLI: handle the case where user presses Enter before completing OAuth
Currently shows "No tokens found" with no retry option. Could loop and re-prompt.

### Priority 3 — Security audit items
See `docs/SECURITY_AUDIT_REPORT.md` for the full list.

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
