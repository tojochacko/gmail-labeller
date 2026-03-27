# Job Alert Labeling Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically apply a secondary Gmail label `ai-job-alert` to emails detected as job alerts, in addition to the existing `Important`/`Not Important` classification.

**Architecture:** A new `JobAlertDetector` (rule-based, no LLM) checks sender domain and email subject. `BatchClassifier` calls it after applying the main label; if detected, applies the `ai-job-alert` label via the existing `GmailService.apply_label()`. The existing `apply_label()` method already handles arbitrary label names without any changes, so the adapter requires no modification.

**Tech Stack:** Pure Python (no new dependencies). Rule-based detection using domain allowlist and keyword matching.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/services/job_alert_detector.py` | Stateless detector: domain list + subject keyword matching |
| Create | `backend/tests/test_job_alert_detector.py` | Unit tests for detector |
| Modify | `backend/app/services/batch_classifier.py` | Call detector; apply `ai-job-alert` tag after main label |
| Modify | `backend/app/services/__init__.py` | Export `JobAlertDetector` |

---

### Task 1: Write `JobAlertDetector` Tests (TDD)

**Files:**
- Create: `backend/tests/test_job_alert_detector.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_job_alert_detector.py`:

```python
"""Tests for JobAlertDetector."""
import pytest

from backend.app.services.job_alert_detector import JobAlertDetector


@pytest.fixture
def detector() -> JobAlertDetector:
    return JobAlertDetector()


class TestSenderDomainDetection:
    def test_linkedin_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="New jobs for you",
            sender_email="jobs-noreply@linkedin.com",
        )

    def test_indeed_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Weekly digest",
            sender_email="alert@indeed.com",
        )

    def test_glassdoor_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="3 new jobs matching Python Engineer",
            sender_email="noreply@glassdoor.com",
        )

    def test_naukri_is_job_alert(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Jobs for you",
            sender_email="donotreply@naukri.com",
        )

    def test_unknown_domain_not_job_alert(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Hello",
            sender_email="someone@gmail.com",
        )

    def test_domain_check_is_case_insensitive(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Hello",
            sender_email="alert@LinkedIn.com",
        )


class TestSubjectKeywordDetection:
    def test_job_alert_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Your job alert: Python Engineer",
            sender_email="no-reply@randomcompany.com",
        )

    def test_new_jobs_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="5 new jobs matching your profile",
            sender_email="digest@somesite.com",
        )

    def test_job_opportunity_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Exciting job opportunity at Acme Corp",
            sender_email="recruiter@headhunter.io",
        )

    def test_hiring_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="We are hiring! Senior Python Developer",
            sender_email="hr@startup.com",
        )

    def test_jobs_for_you_in_subject(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Jobs for you this week",
            sender_email="digest@jobboard.com",
        )

    def test_unrelated_subject_not_job_alert(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Your invoice is ready",
            sender_email="billing@acme.com",
        )

    def test_subject_check_is_case_insensitive(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="JOB ALERT: Senior Engineer",
            sender_email="hr@company.com",
        )


class TestSnippetDetection:
    def test_snippet_with_job_keyword(self, detector: JobAlertDetector) -> None:
        assert detector.is_job_alert(
            subject="Weekly digest",
            sender_email="digest@somesite.com",
            snippet="We found 3 new jobs matching your search for Python Developer.",
        )

    def test_empty_snippet_not_matched(self, detector: JobAlertDetector) -> None:
        assert not detector.is_job_alert(
            subject="Hello there",
            sender_email="friend@example.com",
            snippet="",
        )

    def test_none_snippet_handled(self, detector: JobAlertDetector) -> None:
        # Should not raise
        result = detector.is_job_alert(
            subject="Meeting tomorrow",
            sender_email="boss@work.com",
            snippet=None,
        )
        assert result is False
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest backend/tests/test_job_alert_detector.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` — `job_alert_detector` does not exist yet.

- [ ] **Step 3: Commit failing tests**

```bash
git add backend/tests/test_job_alert_detector.py
git commit -m "test(job-alert): add failing tests for JobAlertDetector"
```

---

### Task 2: Implement `JobAlertDetector`

**Files:**
- Create: `backend/app/services/job_alert_detector.py`

- [ ] **Step 1: Create the detector**

Create `backend/app/services/job_alert_detector.py`:

```python
"""Rule-based detector for job alert emails."""

from __future__ import annotations

import re

_JOB_SENDER_DOMAINS: frozenset[str] = frozenset(
    [
        "linkedin.com",
        "indeed.com",
        "glassdoor.com",
        "naukri.com",
        "monster.com",
        "ziprecruiter.com",
        "dice.com",
        "wellfound.com",
        "levels.fyi",
        "simplyhired.com",
        "careerbuilder.com",
    ]
)

_JOB_SUBJECT_KEYWORDS: tuple[str, ...] = (
    "job alert",
    "new jobs",
    "jobs matching",
    "job opportunity",
    "career opportunity",
    "new opening",
    "we are hiring",
    "we're hiring",
    "jobs for you",
    "job matches",
    "job posting",
    "job recommendation",
)


class JobAlertDetector:
    """Stateless rule-based detector for job alert emails.

    Checks sender domain and subject/snippet for known job alert signals.
    No LLM calls — fast, private, deterministic.
    """

    def is_job_alert(
        self,
        subject: str,
        sender_email: str,
        snippet: str | None = None,
    ) -> bool:
        """Return True if the email looks like a job alert.

        Args:
            subject: Email subject line.
            sender_email: Sender email address (e.g. "jobs@linkedin.com").
            snippet: Optional short preview of the email body.

        Returns:
            True if this email matches job alert signals.
        """
        if self._matches_sender_domain(sender_email):
            return True
        if self._matches_keywords(subject):
            return True
        if snippet and self._matches_keywords(snippet):
            return True
        return False

    def _matches_sender_domain(self, sender_email: str) -> bool:
        match = re.search(r"@([\w.\-]+)$", sender_email.lower())
        if not match:
            return False
        domain = match.group(1)
        # Check exact domain and parent domain (e.g. "mail.linkedin.com" → "linkedin.com")
        parts = domain.split(".")
        for i in range(len(parts) - 1):
            candidate = ".".join(parts[i:])
            if candidate in _JOB_SENDER_DOMAINS:
                return True
        return False

    def _matches_keywords(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in _JOB_SUBJECT_KEYWORDS)
```

- [ ] **Step 2: Run tests — they should pass**

```bash
uv run pytest backend/tests/test_job_alert_detector.py -v
```

Expected: All tests **PASS**.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/job_alert_detector.py
git commit -m "feat(classifier): add JobAlertDetector for rule-based job alert identification"
```

---

### Task 3: Wire `JobAlertDetector` into `BatchClassifier`

**Files:**
- Modify: `backend/app/services/batch_classifier.py`
- Modify: `backend/app/services/__init__.py`

- [ ] **Step 1: Write a failing integration test**

Add to `backend/tests/test_batch_classifier.py` (create if it doesn't exist):

```python
"""Tests for job alert labeling in BatchClassifier."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from backend.app.services.batch_classifier import BatchClassifier
from backend.app.services.job_alert_detector import JobAlertDetector


SESSION_ID = UUID("00000000-0000-0000-0000-000000000001")
USER_ID = UUID("00000000-0000-0000-0000-000000000002")

JOB_EMAIL_ROW = {
    "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    "gmail_message_id": "gmail-msg-123",
    "subject": "3 new jobs matching Python Engineer",
    "snippet": "Senior Python roles available this week.",
    "sender_email": "jobs-noreply@linkedin.com",
    "sender_domain": "linkedin.com",
}


@pytest.fixture
def mock_repo() -> MagicMock:
    repo = MagicMock()
    repo.update_session_status = AsyncMock()
    repo.fetch_session_emails = AsyncMock(return_value=[JOB_EMAIL_ROW])
    return repo


@pytest.fixture
def mock_db() -> MagicMock:
    db = MagicMock()
    db.fetch_gmail_tokens = AsyncMock(return_value=MagicMock())
    return db


@pytest.fixture
def mock_gmail_service() -> MagicMock:
    svc = MagicMock()
    svc.apply_label = AsyncMock()
    return svc


@pytest.fixture
def mock_agent_service() -> MagicMock:
    svc = MagicMock()
    run = MagicMock()
    run.run_id = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
    svc.trigger_agent_run = AsyncMock(return_value=run)
    result = MagicMock()
    result.result_payload = {"suggestion": "Important", "confidence": 0.9}
    svc.get_agent_run = AsyncMock(return_value=result)
    return svc


@pytest.mark.asyncio
async def test_job_alert_label_applied_in_addition_to_main_label(
    mock_repo, mock_db, mock_gmail_service, mock_agent_service
) -> None:
    """Job alert emails should receive both the main label and ai-job-alert."""
    classifier = BatchClassifier(
        session_repo=mock_repo,
        db=mock_db,
        agent_service=mock_agent_service,
        gmail_service=mock_gmail_service,
    )

    await classifier.run_batch(session_id=SESSION_ID, user_id=USER_ID)

    # apply_label should be called twice: once for "Important", once for "ai-job-alert"
    assert mock_gmail_service.apply_label.call_count == 2
    call_labels = [
        call.kwargs.get("label_id") or call.args[1]
        for call in mock_gmail_service.apply_label.call_args_list
    ]
    assert "Important" in call_labels
    assert "ai-job-alert" in call_labels


@pytest.mark.asyncio
async def test_non_job_alert_does_not_get_tag(
    mock_repo, mock_db, mock_gmail_service, mock_agent_service
) -> None:
    """Regular emails should only receive the main classification label."""
    normal_email = {
        "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
        "gmail_message_id": "gmail-msg-456",
        "subject": "Your invoice from Acme Corp",
        "snippet": "Invoice #1234 is attached.",
        "sender_email": "billing@acme.com",
        "sender_domain": "acme.com",
    }
    mock_repo.fetch_session_emails = AsyncMock(return_value=[normal_email])

    classifier = BatchClassifier(
        session_repo=mock_repo,
        db=mock_db,
        agent_service=mock_agent_service,
        gmail_service=mock_gmail_service,
    )

    await classifier.run_batch(session_id=SESSION_ID, user_id=USER_ID)

    assert mock_gmail_service.apply_label.call_count == 1
    call_label = (
        mock_gmail_service.apply_label.call_args.kwargs.get("label_id")
        or mock_gmail_service.apply_label.call_args.args[1]
    )
    assert call_label == "Important"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest backend/tests/test_batch_classifier.py -v -k "job_alert" 2>&1 | tail -20
```

Expected: FAIL — `BatchClassifier` doesn't call `apply_label` twice yet.

- [ ] **Step 3: Update `BatchClassifier`**

In `backend/app/services/batch_classifier.py`:

**Add import at top:**
```python
from .job_alert_detector import JobAlertDetector
```

**Add `_job_alert_detector` to `__init__`:**
```python
def __init__(
    self,
    session_repo: SessionRepository,
    db: DBService,
    agent_service: AgentService,
    gmail_service: GmailService,
    email_filter: LocalEmailFilter | None = None,
    job_alert_detector: JobAlertDetector | None = None,
) -> None:
    self._repo = session_repo
    self._supabase = db
    self._agent_service = agent_service
    self._gmail_service = gmail_service
    self._email_filter = email_filter or LocalEmailFilter()
    self._job_alert_detector = job_alert_detector or JobAlertDetector()
```

**Add job alert check after the main label is applied (after line `logger.debug("Applied '%s' to Gmail msg %s", suggestion, gmail_message_id)`):**

```python
                # Apply ai-job-alert tag if detected
                if tokens and self._job_alert_detector.is_job_alert(
                    subject=email_row.get("subject", ""),
                    sender_email=email_row.get("sender_email", ""),
                    snippet=email_row.get("snippet") or "",
                ):
                    try:
                        await self._gmail_service.apply_label(
                            message_id=gmail_message_id,
                            label_id="ai-job-alert",
                            tokens=tokens,
                            user_id=str(user_id),
                        )
                        logger.info("Applied 'ai-job-alert' tag to %s", gmail_message_id)
                    except Exception as tag_err:
                        logger.warning(
                            "Failed to apply ai-job-alert tag for %s: %s",
                            gmail_message_id,
                            tag_err,
                        )
```

Place this block immediately after the `except Exception as label_err:` block that wraps the main label application, at the same indentation level (inside the `try:` block for the email).

- [ ] **Step 4: Run tests**

```bash
uv run pytest backend/tests/test_batch_classifier.py -v 2>&1 | tail -20
```

Expected: All pass.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest backend/tests/ -v 2>&1 | tail -30
```

Expected: All pass. Fix any regressions.

- [ ] **Step 6: Update `__init__.py` exports**

In `backend/app/services/__init__.py`, add:
```python
from .job_alert_detector import JobAlertDetector
```

And add `"JobAlertDetector"` to the `__all__` list if present.

- [ ] **Step 7: Lint**

```bash
uv run ruff check backend/ --fix && uv run ruff format backend/
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/batch_classifier.py backend/app/services/__init__.py
git commit -m "feat(classifier): apply ai-job-alert label when job alert detected"
```

---

## Self-Review

**Spec coverage:**
- ✅ Detect job alerts from subject and body (snippet) → `JobAlertDetector._matches_keywords()`
- ✅ Detect known job alert senders → `JobAlertDetector._matches_sender_domain()`
- ✅ Apply `ai-job-alert` label → `BatchClassifier` calls `apply_label("ai-job-alert")` after main label
- ✅ Applied on top of existing Important/Not Important label → both calls made independently
- ✅ No changes to existing label application flow — additive only

**Placeholder scan:** None found.

**Type consistency:**
- `JobAlertDetector.is_job_alert(subject, sender_email, snippet)` used consistently in tests and `BatchClassifier`
- `apply_label(message_id, label_id, tokens, user_id)` matches existing `GmailService` signature throughout
