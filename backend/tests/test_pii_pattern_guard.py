"""Tests for PII guards in pattern learning.

Covers:
  - PatternLearningService: snippet excluded from keyword extraction
  - PatternLearningService: personal domains filtered out
  - LabelService: subject is PII-redacted before pattern extraction
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from backend.app.services.pattern_learning_service import PatternLearningService
from backend.app.services.pii_redactor import PIIRedactor, RedactionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_pattern_service() -> PatternLearningService:
    fake_supabase = MagicMock()
    fake_supabase.upsert_label_pattern = AsyncMock()
    return PatternLearningService(fake_supabase)


# ---------------------------------------------------------------------------
# Phase 1 — snippet excluded from keyword extraction
# ---------------------------------------------------------------------------


class TestKeywordExtractionSubjectOnly:
    def setup_method(self) -> None:
        self.svc = _make_pattern_service()

    def test_keywords_extracted_from_subject(self) -> None:
        keywords = self.svc._extract_keywords("Invoice payment overdue")
        assert "invoice" in keywords
        assert "payment" in keywords
        assert "overdue" in keywords

    def test_snippet_content_never_reaches_keywords(self) -> None:
        """_extract_keywords no longer accepts snippet — snippet terms must be absent."""
        keywords = self.svc._extract_keywords("Meeting tomorrow")
        # "snippet-only-term" would only appear if snippet were used
        assert "prescription" not in keywords
        assert "diagnosis" not in keywords

    def test_extract_keywords_signature_has_no_snippet_param(self) -> None:
        import inspect

        sig = inspect.signature(PatternLearningService._extract_keywords)
        assert "snippet" not in sig.parameters, (
            "_extract_keywords must not accept a snippet parameter"
        )


# ---------------------------------------------------------------------------
# Phase 3 — personal domain filter
# ---------------------------------------------------------------------------


class TestPersonalDomainFilter:
    def setup_method(self) -> None:
        self.svc = _make_pattern_service()

    @pytest.mark.parametrize(
        "email",
        [
            "user@gmail.com",
            "user@yahoo.com",
            "user@hotmail.com",
            "user@outlook.com",
            "user@icloud.com",
            "user@protonmail.com",
            "user@googlemail.com",
            "user@ymail.com",
        ],
    )
    def test_personal_domains_return_none(self, email: str) -> None:
        assert self.svc._extract_domain(email) is None

    def test_corporate_domain_extracted(self) -> None:
        assert self.svc._extract_domain("user@acmecorp.com") == "acmecorp.com"

    def test_subdomain_corporate_extracted(self) -> None:
        assert self.svc._extract_domain("user@mail.acmecorp.com") == "mail.acmecorp.com"

    def test_invalid_email_returns_none(self) -> None:
        assert self.svc._extract_domain("not-an-email") is None


# ---------------------------------------------------------------------------
# Phase 2 — LabelService pre-redacts subject before pattern extraction
# ---------------------------------------------------------------------------


class TestLabelServicePreRedactsSubject:
    def _make_label_service(self, redactor: PIIRedactor):
        from backend.app.services.label_service import LabelService

        fake_supabase = MagicMock()
        fake_supabase.fetch_gmail_tokens = AsyncMock(return_value=MagicMock())
        fake_supabase.upsert_label_pattern = AsyncMock()

        fake_gmail = MagicMock()
        fake_gmail.apply_label = AsyncMock()

        fake_pattern_svc = MagicMock()
        fake_pattern_svc.extract_and_store_patterns = AsyncMock()

        svc = LabelService(
            gmail_service=fake_gmail,
            supabase=fake_supabase,
            pattern_service=fake_pattern_svc,
            pii_redactor=redactor,
        )
        return svc, fake_pattern_svc, fake_supabase

    @pytest.mark.asyncio
    async def test_redacted_subject_passed_to_pattern_service(self) -> None:
        """Subject with PII should arrive at pattern service already redacted."""
        redactor = MagicMock(spec=PIIRedactor)
        redactor.redact.return_value = RedactionResult(
            text="Meeting with <PERSON>",
            entities_found=1,
            entity_counts={"PERSON": 1},
        )

        svc, fake_pattern_svc, fake_supabase = self._make_label_service(redactor)

        from backend.app.schemas.email import EmailItem

        email = EmailItem(
            id=uuid4(),
            gmail_message_id="msg-1",
            thread_id="thread-1",
            subject="Meeting with John Smith",
            snippet="Hi John, let's catch up.",
            sender_email="boss@acmecorp.com",
            received_at=datetime.now(timezone.utc),
        )
        fake_supabase.fetch_email_by_gmail_id = AsyncMock(return_value=email)

        await svc._extract_patterns_after_labeling(
            user_id=uuid4(),
            gmail_message_id="msg-1",
            applied_label="Important",
        )

        redactor.redact.assert_called_once_with("Meeting with John Smith")

        call_args = fake_pattern_svc.extract_and_store_patterns.call_args
        request = call_args.kwargs["request"] if call_args.kwargs else call_args[0][0]
        assert request.email_subject == "Meeting with <PERSON>"

    @pytest.mark.asyncio
    async def test_snippet_is_not_passed_to_pattern_service(self) -> None:
        """email_snippet must be None in the extraction request."""
        redactor = MagicMock(spec=PIIRedactor)
        redactor.redact.return_value = RedactionResult(
            text="Invoice overdue", entities_found=0
        )

        svc, fake_pattern_svc, fake_supabase = self._make_label_service(redactor)

        from backend.app.schemas.email import EmailItem

        email = EmailItem(
            id=uuid4(),
            gmail_message_id="msg-2",
            thread_id="thread-2",
            subject="Invoice overdue",
            snippet="Dear customer, your invoice from Dr. Adams is overdue.",
            sender_email="billing@acmecorp.com",
            received_at=datetime.now(timezone.utc),
        )
        fake_supabase.fetch_email_by_gmail_id = AsyncMock(return_value=email)

        await svc._extract_patterns_after_labeling(
            user_id=uuid4(),
            gmail_message_id="msg-2",
            applied_label="Important",
        )

        call_args = fake_pattern_svc.extract_and_store_patterns.call_args
        request = call_args.kwargs["request"] if call_args.kwargs else call_args[0][0]
        assert request.email_snippet is None
