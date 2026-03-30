# PRIMER

Session handoff document. Updated at the end of each session.

---

## What Was Done This Session

### HIGH-04: PII Data Exposure (complete)

Fixed PII leakage in logging, LLM calls, and database ingestion:

1. **Added `is_available()` to `PIIRedactor`** (`backend/app/services/pii_redactor.py`):
   - Lazy initialization now checks if Presidio is actually available before initializing
   - Returns `False` if Presidio not installed or import fails

2. **Startup validator in `Settings`** (`backend/app/config.py`):
   - Validates on app startup that if `OPENAI_API_KEY` is set, Presidio must be available
   - Fails fast with clear error message instead of silently passing unredacted data to LLM

3. **Removed PII-containing logs from `batch_classifier.py`**:
   - Line 99-106: Removed subject from local filter log; now uses `email_id_str`
   - Line 172-174: Removed subject from classification log; now uses `email_id_str`
   - All INFO logs now safe (no PII leakage)

4. **Added PII redaction at email ingestion** (`backend/app/services/email_service.py`):
   - `EmailService.fetch_emails()` now redacts `subject`, `snippet`, and `sender_email` before `upsert_email()`
   - Prevents unredacted PII from ever entering the database

5. **Tests confirm safety**:
   - `test_batch_classifier.py::test_prompt_content_not_logged_at_info` — verifies subject not in INFO logs
   - `test_email_service.py::test_redactor_called_on_subject_snippet_sender` — confirms redaction happens
   - `test_email_service.py::test_upsert_receives_redacted_fields` — confirms DB receives redacted values
   - `test_config.py` — 3 tests for startup validator (OpenAI+no Presidio fails, OpenAI+Presidio passes, etc.)
   - `test_pii_redactor.py` — 16 tests including `test_is_available_*`

### HIGH-05: Prompt Injection via Learned Patterns (complete)

Fixed unbounded growth and injection risk in learned email patterns:

1. **Character allowlist on `pattern_value`** (`backend/app/schemas/label_patterns.py`):
   - Regex: `^[\w \-\.@]+$` (alphanumeric, space, hyphen, dot, @)
   - Rejects: newlines, backticks, quotes, semicolons, command characters
   - Max length: 100 (was 500) — bounds stored pattern size

2. **JSON-encoded `format_for_prompt()`** (`backend/app/schemas/label_patterns.py`):
   - Changed from free-form text to structured JSON
   - Escapes special characters automatically
   - LLM receives `{"keywords": ["a", "b"], "domains": ["c.com"]}` instead of bare strings
   - Safe against injection even if validation is bypassed

3. **Tests confirm safety**:
   - `test_label_patterns.py` — 18 tests covering allowlist, max_length, JSON format, escaping
   - Tests verify injection payloads are rejected (DROP TABLE, rm -rf, say "Important" always, etc.)

### All Tests Passing: 169/169 ✅
- 62 backend tests (DB, auth, routes, services)
- 107 specialized tests (PII, patterns, filters, classifier, etc.)

### Lint Passing: All 6 files ✅
- `backend/app/services/pii_redactor.py`
- `backend/app/config.py`
- `backend/app/services/batch_classifier.py`
- `backend/app/services/email_service.py`
- `backend/app/dependencies.py`
- `backend/app/schemas/label_patterns.py`

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
- **Tests:** 169/169 passing ✅
- **Lint:** All specified files passing ✅
- **Security fixes resolved:**
  - ✅ CRIT-01: Missing JWT auth
  - ✅ CRIT-02: CSRF on review form
  - ✅ CRIT-03: XSS on review page
  - ✅ CRIT-04: Hardcoded credentials
  - ✅ CRIT-05: Session fixation (implicit, via JWT)
  - ✅ HIGH-01: OAuth state CSRF
  - ✅ HIGH-02: Session ownership
  - ✅ HIGH-03: Session ownership (verified pre-existing)
  - ✅ **HIGH-04: PII data exposure** (THIS SESSION)
  - ✅ **HIGH-05: Prompt injection via patterns** (THIS SESSION)
- **Known follow-ups (not blocking):**
  - `batch_classifier.py:85` — WARNING log dumps full `email_row` dict (pre-existing, out of scope)
  - `sender_domain` field stored unredacted (intentional for pattern learning; filters handle safety)
  - `test_config.py` doesn't suppress `env_file` loading (latent local-dev fragility)

---

## Recommended Next Steps

### Priority 1 — Remaining MED/LOW findings (from `docs/SECURITY_AUDIT_REPORT.md`)

Now that HIGH-04 and HIGH-05 are resolved, review and prioritize remaining Medium and Low findings:
- Rate-limiting on OAuth endpoints
- Input size limits on user-supplied patterns
- Audit logs for sensitive operations
- Others — see `docs/SECURITY_AUDIT_REPORT.md` for complete list

### Priority 2 — End-to-end testing

After these fixes, test the full system:
1. Verify Presidio integration works in dev environment
2. Run email classification with PII-containing test data
3. Verify patterns are extracted from subjects only (not snippets)
4. Verify pattern injection attempts fail validation

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
- `2026-03-30-high-04-pii-exposure.md` — completed ✅
- `2026-03-30-high-05-prompt-injection.md` — completed ✅
