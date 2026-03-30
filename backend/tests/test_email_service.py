"""Tests for EmailService ingestion-time PII redaction."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.app.schemas.email import EmailItem
from backend.app.services.email_service import EmailService


def _make_raw_message(subject: str, snippet: str, sender: str) -> dict:
    return {
        "id": "gmail-msg-001",
        "threadId": "thread-001",
        "snippet": snippet,
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "Date", "value": "Mon, 01 Jan 2024 10:00:00 +0000"},
            ]
        },
    }


@pytest.fixture
def mock_gmail_svc():
    svc = MagicMock()
    svc.list_messages = AsyncMock(
        return_value=[
            _make_raw_message(
                subject="Invoice from John Smith",
                snippet="Hi, please find attached invoice for john@example.com",
                sender="john.smith@vendor.com",
            )
        ]
    )
    return svc


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.fetch_gmail_tokens = AsyncMock(return_value=MagicMock())
    db.fetch_email_by_gmail_id = AsyncMock(return_value=None)
    db.upsert_email = AsyncMock()
    return db


@pytest.fixture
def mock_redactor():
    redactor = MagicMock()
    redactor.redact = MagicMock(
        side_effect=lambda text: MagicMock(text=f"[REDACTED:{text[:10]}]")
    )
    return redactor


@pytest.mark.asyncio
async def test_redactor_called_on_subject_snippet_sender(
    mock_gmail_svc, mock_db, mock_redactor
) -> None:
    """PIIRedactor.redact must be called with subject, snippet, and sender_email."""
    svc = EmailService(mock_gmail_svc, mock_db, pii_redactor=mock_redactor)

    await svc.fetch_latest_emails(user_id=uuid4())

    redact_calls = [c.args[0] for c in mock_redactor.redact.call_args_list]
    assert any("Invoice from John Smith" in c for c in redact_calls), "subject not redacted"
    assert any("john@example.com" in c for c in redact_calls), "snippet not redacted"
    assert any("john.smith@vendor.com" in c for c in redact_calls), "sender not redacted"


@pytest.mark.asyncio
async def test_upsert_receives_redacted_fields(
    mock_gmail_svc, mock_db, mock_redactor
) -> None:
    """upsert_email must be called with the redacted values, not originals."""
    svc = EmailService(mock_gmail_svc, mock_db, pii_redactor=mock_redactor)

    await svc.fetch_latest_emails(user_id=uuid4())

    assert mock_db.upsert_email.called
    stored: EmailItem = mock_db.upsert_email.call_args.args[1]
    # Original PII must not reach the DB
    assert "John Smith" not in (stored.subject or "")
    assert "john@example.com" not in (stored.snippet or "")
    assert "john.smith@vendor.com" not in (stored.sender_email or "")
