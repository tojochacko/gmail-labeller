# CRIT-04: Stored XSS in Review UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate stored XSS in the review page by applying `html.escape()` to every user-controlled value interpolated into the HTML template.

**Architecture:** The review page is a single server-rendered HTML string built in `review_page()` via f-string interpolation. Four injection points accept attacker-controlled data: email subject, sender address, AI suggestion label, and Gmail message ID. The fix adds `import html` (stdlib, no new dependency) and replaces all raw f-string interpolations with `html.escape()`-wrapped equivalents. Truncation for display is applied *before* escaping to avoid splitting HTML entities.

**Tech Stack:** Python stdlib `html.escape()`, pytest, FastAPI `dependency_overrides`

---

## File Map

| Action | File | Responsibility |
|---|---|---|
| **Modify** | `backend/app/routes/review.py` | Apply `html.escape()` to all user-data HTML interpolations |
| **Modify** | `backend/tests/test_routes.py` | XSS escaping tests for subject, sender, suggestion, gmail_message_id |

---

## Task 1: Write failing XSS tests

**Files:**
- Modify: `backend/tests/test_routes.py`

### Background

The review page is served by `GET /api/review/{session_id}`. It requires a valid JWT (`authed_client` handles this). The route depends on `ClassificationSessionService` to fetch session data and review items.

For these tests, we override `get_classification_session_service` inline per-test with a minimal fake class. The fake ignores `session_id` and returns whatever data we configure.

- [ ] **Step 1: Read the end of `test_routes.py` to find the append point**

```bash
docker compose exec backend uv run pytest backend/tests/test_routes.py -q --collect-only 2>&1 | tail -20
```

- [ ] **Step 2: Add the XSS tests to `backend/tests/test_routes.py`**

Append the following to the end of the file:

```python
# ---------------------------------------------------------------------------
# Review page — XSS escaping
# ---------------------------------------------------------------------------

def test_review_page_escapes_xss_in_subject(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """Email subject with an XSS payload must be HTML-escaped in the rendered page."""
    from datetime import datetime, timezone

    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [
                {
                    "email": EmailItem(
                        id=uuid4(),
                        gmail_message_id="msg-1",
                        thread_id="t-1",
                        subject='<script>alert("xss")</script>',
                        received_at=datetime.now(timezone.utc),
                    ),
                    "suggestion": "Important",
                    "confidence": 0.9,
                }
            ]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert "<script>" not in response.text
        assert "&lt;script&gt;" in response.text
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)


def test_review_page_escapes_xss_in_sender(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """Sender email with an XSS payload must be HTML-escaped in the rendered page."""
    from datetime import datetime, timezone

    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [
                {
                    "email": EmailItem(
                        id=uuid4(),
                        gmail_message_id="msg-1",
                        thread_id="t-1",
                        subject="Normal subject",
                        sender_email='<img src=x onerror=alert(1)>@evil.com',
                        received_at=datetime.now(timezone.utc),
                    ),
                    "suggestion": "Not Important",
                    "confidence": 0.5,
                }
            ]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert "<img" not in response.text
        assert "&lt;img" in response.text
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)


def test_review_page_escapes_xss_in_suggestion(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """AI suggestion label with HTML must be escaped in the rendered page."""
    from datetime import datetime, timezone

    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [
                {
                    "email": EmailItem(
                        id=uuid4(),
                        gmail_message_id="msg-1",
                        thread_id="t-1",
                        subject="Normal subject",
                        received_at=datetime.now(timezone.utc),
                    ),
                    "suggestion": '<b onclick=alert(1)>Important</b>',
                    "confidence": 0.8,
                }
            ]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert "<b " not in response.text
        assert "&lt;b " in response.text
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)


def test_review_page_escapes_xss_in_gmail_message_id(
    authed_client: TestClient,
    auth_user_id: UUID,
) -> None:
    """gmail_message_id with HTML must be escaped in data-gmail-id attribute."""
    from datetime import datetime, timezone

    from backend.app.dependencies import get_classification_session_service
    from backend.app.schemas import EmailItem

    class _FakeSvc:
        async def get_session(self, _: UUID) -> dict:
            return {"user_id": str(auth_user_id)}

        async def get_session_review_items(self, _: UUID) -> list:
            return [
                {
                    "email": EmailItem(
                        id=uuid4(),
                        gmail_message_id='"><script>alert(1)</script>',
                        thread_id="t-1",
                        subject="Normal subject",
                        received_at=datetime.now(timezone.utc),
                    ),
                    "suggestion": "Important",
                    "confidence": 0.9,
                }
            ]

    authed_client.app.dependency_overrides[get_classification_session_service] = _FakeSvc
    try:
        response = authed_client.get(f"/api/review/{uuid4()}")
        assert response.status_code == 200
        assert "<script>" not in response.text
        assert "&lt;script&gt;" in response.text
    finally:
        authed_client.app.dependency_overrides.pop(get_classification_session_service, None)
```

- [ ] **Step 3: Run tests to verify they FAIL**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_subject \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_sender \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_suggestion \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_gmail_message_id \
  -v
```

Expected: all 4 FAIL. Each test asserts `"<script>" not in response.text` but the current code interpolates raw values, so `<script>` IS present.

- [ ] **Step 4: Commit the failing tests**

```bash
git add backend/tests/test_routes.py
git commit -m "test(security): add failing XSS escaping tests for review page (CRIT-04)"
```

---

## Task 2: Apply `html.escape()` to the review page template

**Files:**
- Modify: `backend/app/routes/review.py:1-10` (add import)
- Modify: `backend/app/routes/review.py:54-80` (replace interpolation block)

### Exact changes

- [ ] **Step 1: Add `import html` to the imports in `review.py`**

The current imports block (top of file) starts with:

```python
"""Human review web UI and correction API for classified emails."""

from __future__ import annotations

import logging
from uuid import UUID
```

Add `import html` so it becomes:

```python
"""Human review web UI and correction API for classified emails."""

from __future__ import annotations

import html
import logging
from uuid import UUID
```

- [ ] **Step 2: Replace the row-building block in `review_page()`**

Find and replace the entire block from `rows_html = ""` through the closing `</tr>"""` (lines 54–80). The **current** code:

```python
    rows_html = ""
    for item in review_items:
        email = item["email"]
        suggestion = item["suggestion"] or "Uncategorized"
        confidence = item["confidence"]
        label_color = (
            "#22c55e" if suggestion == "Important"
            else "#f59e0b" if suggestion == "Not Important"
            else "#6b7280"
        )
        confidence_str = f"{confidence:.0%}" if confidence is not None else "–"
        subject_escaped = (email.subject or "(no subject)").replace('"', "&quot;")
        sender_escaped = (email.sender_email or "–").replace('"', "&quot;")
        rows_html += f"""
        <tr data-email-id="{email.id}" data-gmail-id="{email.gmail_message_id}">
          <td title="{subject_escaped}">{(email.subject or "(no subject)")[:60]}</td>
          <td title="{sender_escaped}">{(email.sender_email or "–")[:35]}</td>
          <td class="label-cell" style="color:{label_color};font-weight:600">{suggestion}</td>
          <td class="conf-cell">{confidence_str}</td>
          <td class="actions">
            <button class="btn-correct" data-new-label="Important"
              onclick="correct(this,'Important')">✓ Important</button>
            <button class="btn-correct" data-new-label="Not Important"
              onclick="correct(this,'Not Important')">✗ Not Important</button>
            <button class="btn-approve" onclick="approve(this)">👍 OK</button>
          </td>
        </tr>"""
```

Replace with:

```python
    rows_html = ""
    for item in review_items:
        email = item["email"]
        suggestion = item["suggestion"] or "Uncategorized"
        confidence = item["confidence"]
        label_color = (
            "#22c55e" if suggestion == "Important"
            else "#f59e0b" if suggestion == "Not Important"
            else "#6b7280"
        )
        confidence_str = f"{confidence:.0%}" if confidence is not None else "–"
        subject_raw = email.subject or "(no subject)"
        subject_title = html.escape(subject_raw)
        subject_cell = html.escape(subject_raw[:60])
        sender_raw = email.sender_email or "–"
        sender_title = html.escape(sender_raw)
        sender_cell = html.escape(sender_raw[:35])
        gmail_id_safe = html.escape(email.gmail_message_id or "")
        suggestion_safe = html.escape(suggestion)
        rows_html += f"""
        <tr data-email-id="{email.id}" data-gmail-id="{gmail_id_safe}">
          <td title="{subject_title}">{subject_cell}</td>
          <td title="{sender_title}">{sender_cell}</td>
          <td class="label-cell" style="color:{label_color};font-weight:600">{suggestion_safe}</td>
          <td class="conf-cell">{confidence_str}</td>
          <td class="actions">
            <button class="btn-correct" data-new-label="Important"
              onclick="correct(this,'Important')">✓ Important</button>
            <button class="btn-correct" data-new-label="Not Important"
              onclick="correct(this,'Not Important')">✗ Not Important</button>
            <button class="btn-approve" onclick="approve(this)">👍 OK</button>
          </td>
        </tr>"""
```

**Key differences:**
- `subject_raw[:60]` truncation happens **before** `html.escape()` — avoids splitting an HTML entity mid-string
- `subject_title` (full length) and `subject_cell` (truncated) are separate escaped variables
- `suggestion_safe` escapes the AI label before it goes into the `<td>`
- `gmail_id_safe` escapes the message ID before it goes into the `data-gmail-id` attribute
- The old `.replace('"', "&quot;")` approach is dropped entirely — `html.escape()` handles `&`, `<`, `>`, `"`, and `'`

- [ ] **Step 3: Run the 4 XSS tests to verify they now PASS**

```bash
docker compose exec backend uv run pytest \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_subject \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_sender \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_suggestion \
  backend/tests/test_routes.py::test_review_page_escapes_xss_in_gmail_message_id \
  -v
```

Expected: all 4 PASS.

- [ ] **Step 4: Run full test suite**

```bash
docker compose exec backend uv run pytest backend/tests/ -q
```

Expected: all tests pass (120 + 4 new = 124 or similar).

- [ ] **Step 5: Lint**

```bash
docker compose exec backend uv run ruff check backend/app/routes/review.py --fix \
  && docker compose exec backend uv run ruff format backend/app/routes/review.py
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routes/review.py
git commit -m "fix(security): apply html.escape() to all user data in review page (CRIT-04)"
```

---

## Task 3: Update security audit report and PRIMER

**Files:**
- Modify: `docs/SECURITY_AUDIT_REPORT.md` — mark CRIT-04 as fixed
- Modify: `PRIMER.md` — update current state and next steps

- [ ] **Step 1: Update the status table in `docs/SECURITY_AUDIT_REPORT.md`**

Find:
```
| CRIT-04 | Stored XSS in review UI | **NOT FIXED** |
```

Replace with:
```
| CRIT-04 | Stored XSS in review UI | **FIXED** — html.escape() applied to all user data in review template |
```

- [ ] **Step 2: Update `PRIMER.md`**

In the "Recommended Next Steps" section, remove CRIT-04 from Priority 1 (it's done), and update the "Current State" tests count to the new passing count.

- [ ] **Step 3: Commit**

```bash
git add docs/SECURITY_AUDIT_REPORT.md PRIMER.md
git commit -m "docs: mark CRIT-04 fixed in security audit after html.escape() remediation"
```

---

## Self-Review

**1. Spec coverage:**

| Requirement | Task |
|---|---|
| `email.subject` escaped in `<td>` cell | Task 2 — `subject_cell = html.escape(subject_raw[:60])` |
| `email.subject` escaped in `title=""` attr | Task 2 — `subject_title = html.escape(subject_raw)` |
| `email.sender_email` escaped in `<td>` cell | Task 2 — `sender_cell = html.escape(sender_raw[:35])` |
| `email.sender_email` escaped in `title=""` attr | Task 2 — `sender_title = html.escape(sender_raw)` |
| `suggestion` (AI label) escaped in `<td>` | Task 2 — `suggestion_safe = html.escape(suggestion)` |
| `email.gmail_message_id` escaped in `data-gmail-id` | Task 2 — `gmail_id_safe = html.escape(...)` |
| Truncation happens before escaping | Task 2 — `subject_raw[:60]` then `html.escape()` |
| Tests cover all 4 injection points | Task 1 — 4 separate tests |
| Tests are TDD (fail before fix) | Task 1 Step 3 verifies failure; Task 2 Step 3 verifies pass |

**2. Placeholder scan:** None found. All steps contain complete code.

**3. Type consistency:**
- `html.escape()` takes `str` and returns `str` — consistent with f-string usage ✓
- `subject_raw[:60]` on a `str` returns `str` — correct ✓
- `email.gmail_message_id or ""` — handles the `Optional[str]` field ✓ (though `gmail_message_id` is required per schema — the `or ""` is a safe guard)
