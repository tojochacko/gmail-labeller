"""Label application service with pattern learning support."""

from __future__ import annotations

from typing import cast
from uuid import UUID

import logging

from ..schemas.email import LabelType
from ..schemas.label_patterns import PatternExtractionRequest
from ..schemas.labels import ApplyLabelRequest, ApplyLabelResponse
from ..schemas.oauth import GmailTokens
from .gmail_toolkit import GmailService
from .pattern_learning_service import PatternLearningService
from .pii_redactor import PIIRedactor
from .db_service import DBService as SupabaseService


logger = logging.getLogger(__name__)


class LabelService:
    """Apply Gmail labels via Composio with intelligent pattern learning.

    Supports both manual labeling and re-marking with accelerated learning (2x weight).
    """

    def __init__(
        self,
        gmail_service: GmailService,
        supabase: SupabaseService,
        pattern_service: PatternLearningService | None = None,
        pii_redactor: PIIRedactor | None = None,
    ) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase
        self._pattern_service = pattern_service or PatternLearningService(supabase)
        self._pii_redactor = pii_redactor or PIIRedactor()

    async def apply_label(self, request: ApplyLabelRequest) -> ApplyLabelResponse:
        """Apply a Gmail label and trigger pattern learning.

        Args:
            request: Label application request with user_id, message_id, and label_name

        Returns:
            ApplyLabelResponse with success status and applied label

        Raises:
            ValueError: If user has no Gmail tokens
        """
        tokens = await self._ensure_tokens(request.user_id)
        label_id = request.gmail_label_id or request.label_name

        await self._gmail_service.apply_label(
            message_id=request.gmail_message_id,
            label_id=label_id,
            tokens=tokens,
            user_id=str(request.user_id),
        )
        logger.info("Gmail label '%s' applied to message %s", label_id, request.gmail_message_id)

        try:
            await self._extract_patterns_after_labeling(
                user_id=request.user_id,
                gmail_message_id=request.gmail_message_id,
                applied_label=cast(LabelType, request.label_name),
            )
        except Exception as e:
            logger.warning("Pattern extraction failed (non-fatal): %s", e)

        return ApplyLabelResponse(success=True, label=label_id)

    async def _extract_patterns_after_labeling(
        self, user_id: UUID, gmail_message_id: str, applied_label: LabelType
    ) -> None:
        """
        Extract patterns from labeled email.

        This method intentionally does not raise exceptions to avoid blocking
        the label application workflow.
        """
        try:
            # Fetch email from database
            email = await self._supabase.fetch_email_by_gmail_id(
                user_id=user_id, gmail_message_id=gmail_message_id
            )

            if not email:
                logger.warning(
                    f"Email {gmail_message_id} not found in database. Skipping pattern extraction."
                )
                return

            # Check if sender_email is available
            if not email.sender_email:
                logger.warning(
                    f"Sender email not available for email {email.id}. Skipping pattern extraction."
                )
                return

            # Redact PII from subject before it is stored as learned patterns.
            # This runs at the source so the DB never holds raw personal data.
            # Snippet is intentionally excluded — body text has higher PII density.
            raw_subject = email.subject or ""
            redacted = self._pii_redactor.redact(raw_subject)
            if redacted.entities_found:
                logger.info(
                    "Redacted %d PII entities from subject before pattern extraction "
                    "(email %s): %s",
                    redacted.entities_found,
                    email.id,
                    redacted.entity_counts,
                )

            extraction_request = PatternExtractionRequest(
                email_id=email.id,
                label=applied_label,
                sender_email=email.sender_email,
                email_subject=redacted.text,
                email_snippet=None,
            )

            await self._pattern_service.extract_and_store_patterns(
                request=extraction_request,
                user_id=user_id,
            )

            logger.info(f"Patterns extracted for email {email.id}")

        except Exception as e:
            # Don't fail the label application if pattern extraction fails
            logger.warning(f"Pattern extraction failed: {e}")

    async def _ensure_tokens(self, user_id: UUID) -> GmailTokens:
        tokens = await self._supabase.fetch_gmail_tokens(user_id)
        if not tokens:
            raise ValueError("No Gmail tokens found for user. Complete onboarding first.")
        return tokens
