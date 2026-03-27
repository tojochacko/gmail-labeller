"""Tests for job alert labeling in BatchClassifier."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from backend.app.services.batch_classifier import BatchClassifier


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
