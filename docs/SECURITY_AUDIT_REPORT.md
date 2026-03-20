# Security Audit Report

**Project:** autogen-test (FastAPI Gmail Labeler Backend)
**Audit Date:** 2026-03-20
**Auditor:** Application Security Review
**Scope:** Backend API (`/backend/app/`) — routes, services, schemas, config, OAuth flow, database operations, PII handling

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Scope and Methodology](#scope-and-methodology)
3. [Risk Rating Matrix](#risk-rating-matrix)
4. [Critical Findings](#critical-findings)
5. [High Findings](#high-findings)
6. [Medium Findings](#medium-findings)
7. [Low Findings](#low-findings)
8. [Positive Security Controls](#positive-security-controls)
9. [Priority Action Plan](#priority-action-plan)

---

## Executive Summary

A comprehensive Application Security review was conducted on the backend of the autogen-test project. The audit identified **3 Critical**, **2 High**, **5 Medium**, and **2 Low** severity vulnerabilities.

The most severe finding is the **complete absence of authentication and authorization** across all API endpoints. Any caller with knowledge of the API can impersonate any user, read their emails, apply labels to their inbox, and destroy their sessions. Until this is resolved, all other findings are secondary — the attack surface is fully open.

The project does demonstrate several good security practices (Fernet encryption for tokens, PII redaction via Presidio, `SecretStr` in config), but these controls are undermined by the missing authentication layer.

---

## Scope and Methodology

### Files Reviewed

| Area | Files |
|---|---|
| Routes | `routes/emails.py`, `routes/labels.py`, `routes/oauth.py`, `routes/sessions.py`, `routes/review.py`, `routes/debug.py`, `routes/patterns.py` |
| Services | `services/supabase_service.py`, `services/label_service.py`, `services/pii_redactor.py`, `services/pattern_learning_service.py`, `services/local_email_filter.py`, `services/gmail_toolkit.py`, `services/agent_service.py` |
| Config | `app/config.py`, `app/main.py` |
| Schemas | `schemas/` (all Pydantic models) |
| Database | `database/supabase_schema.sql` |
| Config | `config/env.example` |

### Methodology

- Manual code review of all backend source files
- OWASP Top 10 checklist applied
- Authentication and authorization flow analysis
- Input validation review
- Secrets and configuration management review
- Error handling and information disclosure review
- Logging and observability review

---

## Risk Rating Matrix

| Severity | Description |
|---|---|
| **Critical** | Immediate exploitable risk with high business impact. Must be fixed before any production deployment. |
| **High** | Significant risk that could lead to data breach or account takeover. Fix within current sprint. |
| **Medium** | Exploitable under certain conditions. Fix within the next sprint. |
| **Low** | Defense-in-depth or hardening improvements. Fix when convenient. |

---

## Critical Findings

### CRIT-01: No Authentication or Authorization on Any API Endpoint

**Severity:** Critical
**OWASP Category:** A01:2021 – Broken Access Control
**Files Affected:**
- `backend/app/routes/emails.py:18-26`
- `backend/app/routes/labels.py:19-27`
- `backend/app/routes/sessions.py` (all endpoints)
- `backend/app/routes/patterns.py` (all endpoints)

**Description:**
Every route in the backend accepts a `user_id` directly from query parameters or request body without verifying that the caller is actually that user. There is no JWT validation, no session middleware, and no identity verification of any kind.

**Impact:**
Any attacker (or curious user) can call any endpoint with an arbitrary `user_id` and:
- Read another user's emails
- Apply or remove labels on another user's inbox
- View another user's learned patterns
- Access session data belonging to other users

**Proof of Concept:**
```bash
# Fetch another user's emails by supplying their UUID
curl "http://localhost:8000/api/emails?user_id=<victim-uuid>"

# Apply labels to another user's email
curl -X POST "http://localhost:8000/api/labels" \
  -d '{"user_id": "<victim-uuid>", "message_id": "...", "label": "IMPORTANT"}'
```

**Recommendation:**
Implement JWT-based authentication middleware. Verify the authenticated user's identity server-side and compare it against the requested `user_id`. Reject requests where they do not match.

```python
# Example FastAPI dependency for auth
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)) -> str:
    user_id = verify_jwt(token)  # Validate and decode
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user_id
```

---

### CRIT-02: Insecure Direct Object References (IDOR)

**Severity:** Critical
**OWASP Category:** A01:2021 – Broken Access Control
**Files Affected:**
- `backend/app/routes/emails.py`
- `backend/app/routes/labels.py`
- `backend/app/routes/sessions.py`
- `backend/app/routes/patterns.py`

**Description:**
All resource identifiers (user UUIDs, session UUIDs) are accepted from the client without ownership verification. Because UUIDs are not secret (they can be logged, leaked in errors, or enumerated), this constitutes a full IDOR vulnerability.

**Impact:**
Complete cross-user data access. Compounded by CRIT-01, there is no layer preventing unauthorized access to any object in the system.

**Recommendation:**
After implementing authentication (CRIT-01), add ownership checks on every endpoint that accesses user-owned data:

```python
@router.get("/emails")
async def get_emails(user_id: str, current_user: str = Depends(get_current_user)):
    if user_id != current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    # proceed
```

---

### CRIT-03: Unauthenticated Debug Endpoints Exposing Full User Data

**Severity:** Critical
**OWASP Category:** A05:2021 – Security Misconfiguration
**Files Affected:**
- `backend/app/routes/debug.py` (entire file)

**Description:**
Debug routes (`/api/debug/emails/{user_id}` and `/api/debug/agent-runs/{user_id}`) dump raw database records — including email content and agent run payloads — for any user, with zero authorization checks.

**Impact:**
Complete data exfiltration for any user in the system. An attacker can enumerate users and extract all their data through these endpoints.

**Recommendation:**
Remove the debug routes entirely before any deployment. If debug access is required in development, restrict it to:
- Local environment only (check `settings.environment == "development"`)
- Authenticated admin-only access with a separate admin role

---

## High Findings

### HIGH-01: OAuth State Parameter Never Verified (CSRF in OAuth Flow)

**Severity:** High
**OWASP Category:** A01:2021 – Broken Access Control / CSRF
**Files Affected:**
- `backend/app/routes/oauth.py:27-97`

**Description:**
The OAuth flow generates a `state` parameter at `/oauth/start` but never stores it server-side. On the `/oauth/callback` endpoint, the returned `state` is accepted and ignored — it is never compared against the originally issued value.

This means the CSRF protection that `state` is designed to provide is completely absent. An attacker can craft a malicious OAuth callback and link an arbitrary token to a victim's account (account hijacking via OAuth token substitution).

**Impact:**
OAuth account takeover. An attacker who tricks a logged-in user into visiting a crafted URL can link the attacker's Google account token to the victim's application account.

**Recommendation:**
Store the generated state (e.g., in a short-lived database record or signed cookie) and verify it matches on callback:

```python
# On /oauth/start: store state
await store_oauth_state(user_id, state, expires_in=600)

# On /oauth/callback: verify state
stored_state = await get_oauth_state(returned_state)
if not stored_state or stored_state.user_id != expected_user_id:
    raise HTTPException(status_code=400, detail="Invalid OAuth state")
```

---

### HIGH-02: No Ownership Check on Session Cleanup

**Severity:** High
**OWASP Category:** A01:2021 – Broken Access Control
**Files Affected:**
- `backend/app/routes/sessions.py:143-159`

**Description:**
The `DELETE /api/sessions/{session_id}/cleanup` endpoint accepts a `session_id` path parameter and deletes the corresponding session data with no verification that the caller owns that session.

**Impact:**
Any caller who knows (or can guess) a session UUID can destroy another user's active session, causing data loss and service disruption.

**Recommendation:**
After implementing authentication, verify session ownership:

```python
session = await get_session(session_id)
if session.user_id != current_user:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
```

---

## Medium Findings

### MED-01: Overly Permissive CORS Configuration

**Severity:** Medium
**OWASP Category:** A05:2021 – Security Misconfiguration
**Files Affected:**
- `backend/app/main.py:48`

**Description:**
CORS is configured with wildcard allow lists:
```python
allow_methods=["*"]
allow_headers=["*"]
```

**Impact:**
Permits any HTTP method and any header from allowed origins, broadening the attack surface unnecessarily.

**Recommendation:**
Restrict to explicit lists:
```python
allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
allow_headers=["Authorization", "Content-Type", "X-Requested-With"]
```

---

### MED-02: No Rate Limiting on Any Endpoint

**Severity:** Medium
**OWASP Category:** A04:2021 – Insecure Design
**Files Affected:**
- All route files, especially `routes/oauth.py`

**Description:**
No rate limiting is applied to any endpoint. The OAuth endpoints are particularly sensitive — `/oauth/start` and `/oauth/callback` can be called indefinitely without throttling.

**Impact:**
- Brute force enumeration of user IDs
- DoS via resource exhaustion
- Credential stuffing on OAuth flow

**Recommendation:**
Add `slowapi` rate limiting:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/oauth/start")
@limiter.limit("5/minute")
async def oauth_start(request: Request, ...):
    ...
```

---

### MED-03: Sensitive Error Messages Returned to Clients

**Severity:** Medium
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Files Affected:**
- `backend/app/routes/review.py:243`
- `backend/app/routes/sessions.py:74-76`

**Description:**
Internal exceptions are returned directly to API callers:
```python
raise HTTPException(status_code=500, detail=str(e))
```

**Impact:**
Leaks internal implementation details, stack traces, file paths, or database schema information to external callers.

**Recommendation:**
Log the full error server-side, return a generic message to the client:
```python
except Exception as e:
    logger.exception(f"Unexpected error in {endpoint}: {e}")
    raise HTTPException(status_code=500, detail="An internal error occurred.")
```

---

### MED-04: PII Stored Unredacted in the Database

**Severity:** Medium
**OWASP Category:** A02:2021 – Cryptographic Failures / Data Exposure
**Files Affected:**
- `backend/app/services/label_service.py:103-121`

**Description:**
PII redaction (via Microsoft Presidio) is applied before extracting patterns for storage and before LLM calls. However, the original email subjects — which may contain PII (names, account numbers, phone numbers) — are stored unredacted in the `emails` database table.

**Impact:**
The database becomes a PII store. Any breach of the database (or misuse via CRIT-01/CRIT-02) exposes raw PII to unauthorized parties.

**Recommendation:**
Apply PII redaction at email ingestion time, before writing to the database, rather than only before LLM calls.

---

### MED-05: No Input Validation on Gmail Query Parameter

**Severity:** Medium
**OWASP Category:** A03:2021 – Injection
**Files Affected:**
- `backend/app/routes/emails.py:21-24`

**Description:**
The `query` parameter used for Gmail search is passed through to Composio with no validation, no length limit, and no character filtering.

**Impact:**
Malformed or adversarial query strings could cause unexpected behavior in Composio or the Gmail API. Could potentially be used for injection if the query is ever interpolated into a larger string server-side.

**Recommendation:**
Add validation:
```python
query: str = Query(default="", max_length=500, regex=r"^[\w\s:@.\"'()\-]+$")
```

---

## Low Findings

### LOW-01: Debug Logging of Sensitive Email Metadata

**Severity:** Low
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Files Affected:**
- `backend/app/services/email_service.py`
- `backend/app/services/gmail_toolkit.py`

**Description:**
Debug log statements include email subjects, sender addresses, and message IDs. If these logs are forwarded to a log aggregation service (e.g., Datadog, Splunk) without access controls, sensitive user data is exposed.

**Recommendation:**
- Avoid logging email subjects and sender addresses at any log level
- If needed for debugging, use a structured logging approach that masks or hashes PII fields
- Ensure log aggregation services have appropriate access controls

---

### LOW-02: No Startup Validation for FERNET_SECRET_KEY

**Severity:** Low
**OWASP Category:** A05:2021 – Security Misconfiguration
**Files Affected:**
- `backend/app/services/supabase_service.py:649-653`
- `backend/app/config.py`

**Description:**
The Fernet encryption key is read from the environment but is not validated at startup. If `FERNET_SECRET_KEY` is missing or malformed, the application will crash at runtime during the first token encryption/decryption operation rather than failing fast at startup.

**Recommendation:**
Add a startup validation in `config.py`:
```python
from cryptography.fernet import Fernet

@validator("fernet_secret_key")
def validate_fernet_key(cls, v):
    try:
        Fernet(v.get_secret_value().encode())
    except Exception:
        raise ValueError("FERNET_SECRET_KEY is not a valid Fernet key")
    return v
```

---

## Positive Security Controls

The following security measures are correctly implemented and should be maintained:

| Control | Location | Notes |
|---|---|---|
| Fernet encryption for OAuth tokens at rest | `services/supabase_service.py:31, 649-653` | Correctly implemented |
| PII redaction via Microsoft Presidio | `services/pii_redactor.py` | Applied before every LLM call |
| `SecretStr` for sensitive config fields | `app/config.py:22-26, 34, 39` | Prevents secrets appearing in logs/repr |
| Personal provider domains excluded from pattern learning | `services/pattern_learning_service.py:143-159` | Good privacy default |
| Pydantic models for all request validation | `schemas/` | Strong input validation boundary |
| Attachments excluded from Gmail queries | `services/email_service.py:44` | Prevents sensitive file ingestion |
| RLS policies configured on Supabase | `database/supabase_schema.sql` | Row-level security is in place |
| Sensitive/automated emails filtered before LLM | `services/local_email_filter.py` | Bank statements, OTPs skipped |

---

## Priority Action Plan

| Priority | ID | Finding | Effort |
|---|---|---|---|
| P0 | CRIT-01 | Add JWT/session-based authentication middleware | High |
| P0 | CRIT-02 | Add ownership authorization checks on all endpoints | Medium |
| P0 | CRIT-03 | Remove or lock down `/api/debug/*` routes | Low |
| P1 | HIGH-01 | Fix OAuth state verification (CSRF protection) | Medium |
| P1 | HIGH-02 | Add ownership check on session cleanup endpoint | Low |
| P2 | MED-01 | Restrict CORS to explicit allow lists | Low |
| P2 | MED-02 | Add rate limiting with `slowapi` | Medium |
| P2 | MED-03 | Replace `str(e)` in error responses with generic messages | Low |
| P2 | MED-04 | Redact PII at ingestion time, not just before LLM calls | Medium |
| P2 | MED-05 | Add validation and length limit to Gmail query parameter | Low |
| P3 | LOW-01 | Remove or mask PII from debug log statements | Low |
| P3 | LOW-02 | Add Fernet key validation at application startup | Low |

---

## Conclusion

The project has a solid foundation — Fernet encryption, Presidio PII redaction, and Pydantic validation show awareness of security concerns. However, the absence of any authentication or authorization layer is a fundamental gap that makes all other controls ineffective. A determined attacker does not need to bypass encryption or exploit injection flaws — they can simply call the API as any user they choose.

**No production deployment should occur until CRIT-01, CRIT-02, and CRIT-03 are resolved.**

After the P0 findings are addressed, the remaining findings should be worked through in priority order over the following sprints.
