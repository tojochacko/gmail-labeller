# PRIMER

Session handoff document. Updated at the end of each session.

---

## What Was Done This Session

### 1. SQLite + SQLAlchemy Migration (committed before session start)
Replaced Supabase with a self-hosted SQLite database:
- New `backend/app/db/` — SQLAlchemy ORM models (User, GmailToken, Email, AgentRun, LabelPattern, ClassificationSession)
- New `backend/app/services/db_service.py` — `DBService` replacing `SupabaseService`, with Fernet-encrypted token storage
- Alembic migration infrastructure (`alembic.ini`, `backend/alembic/`)
- All services and dependency injection updated to use `DBService`
- 27 async tests added for `DBService`

### 2. Docker Setup
Created containerised dev/test environment:
- `Dockerfile` — Python 3.12-slim + uv, installs all deps including spaCy `en_core_web_lg`
- `docker-compose.yml` — single `backend` service, mounts source, preserves venv in named volume
- `.dockerignore` — excludes `.venv`, `__pycache__`, `data/*.db`, etc.
- Tests run with: `docker compose exec backend uv run pytest backend/tests/ -v`
- Container: `autogen-test-backend-1`

### 3. Gmail API Direct Integration (replaced Composio)
Removed Composio middleware and replaced with direct Google Gmail API:
- `backend/app/services/gmail_toolkit.py` — `ComposioGmailAdapter` replaced by `GmailApiAdapter` using `google-api-python-client`; `GmailService` interface preserved identically
- `backend/app/routes/oauth.py` — simplified to standard OAuth2 only (no Composio-managed branch)
- `backend/app/schemas/oauth.py` — `OAuthCallbackRequest.code` is now required
- `backend/app/config.py` — removed `composio_api_key`, `composio_account_id`
- `pyproject.toml` — removed `composio`, `composio-openai`; added `google-auth-oauthlib`, `google-api-python-client`, `google-auth-httplib2`
- Dead Composio code cleaned from `email_service.py`, `cli.py`, `label_service.py`, `schemas/email.py`, `scripts/`

### 4. Job Alert Labeling (`ai-job-alert`)
Added automatic `ai-job-alert` Gmail label applied on top of Important/Not Important:
- New `backend/app/services/job_alert_detector.py` — stateless rule-based `JobAlertDetector`
  - Domain allowlist: linkedin.com, indeed.com, glassdoor.com, naukri.com, monster.com, ziprecruiter.com, dice.com, wellfound.com, levels.fyi, simplyhired.com, careerbuilder.com
  - Subject/snippet keyword list: "job alert", "new jobs", "jobs matching", "job opportunity", "career opportunity", "new opening", "we are hiring", "we're hiring", "jobs for you", "job matches", "job posting", "job recommendation"
- `BatchClassifier` updated: after main label applied, runs detector; if matched, calls `apply_label("ai-job-alert")`
- 16 unit tests for `JobAlertDetector`, 2 integration tests for `BatchClassifier`

---

## Current State

- **Branch:** `main`
- **Tests:** 95/95 passing in Docker container
- **Docker:** `autogen-test-backend-1` running (`docker compose up -d` from project root to start)

---

## Recommended Next Steps

### Priority 1 — Enhance job alert detection with LLM layer

**Context:** The current `JobAlertDetector` is rule-based (domain + keywords). The user proposed adding a second detection layer using the LLM, giving the system more confidence via two independent signals.

**Design agreed upon:**
- Keep rule-based detection as the fast path (catches clear cases without LLM)
- Update the LLM classification prompt to also return `is_job_alert: true/false`
- Apply `ai-job-alert` if **either** the rule-based detector fires OR the LLM returns `is_job_alert: true`
- When `LocalEmailFilter` skips the LLM (bank statements, OTPs), rule-based detection is the only layer — acceptable since those emails are not job alerts

**Important prompt guidance:** Ask specifically "Is this a job posting, recruiter outreach, or automated job board alert?" — not "is this job-related?" (too broad).

**Files to change:**
- `backend/app/services/batch_classifier.py`:
  - Update `_build_classification_prompt()` to request `is_job_alert` in the JSON response
  - Extract `is_job_alert` from LLM result alongside `suggestion`
  - Update tag condition: `rule_based OR llm_is_job_alert`
- `backend/tests/test_batch_classifier.py` — add test for LLM-detected job alert (rule-based doesn't fire, but LLM returns `is_job_alert: true`)
- No changes needed to `JobAlertDetector`, `gmail_toolkit.py`, or any other file

**Effort:** Small (~20 lines of logic, 3 new tests)

**Implementation plan:** No formal plan doc needed — small enough to implement directly with subagent-driven development.

### Priority 2 — End-to-end testing
The OAuth flow uses real Google credentials. Before production:
1. Set `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI` in `config/.env`
2. Verify redirect URI is registered in Google Cloud Console
3. Run the OAuth flow manually: `POST /oauth/start` → browser → `POST /oauth/callback`
4. Run a batch classification to confirm Gmail label application works

### Priority 3 — Security audit items
See `docs/SECURITY_AUDIT_REPORT.md` for the full list flagged before this session.

---

## Key Commands

```bash
# Start container
docker compose up -d

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
