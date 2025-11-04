"""Label application service."""

from __future__ import annotations

import re
from uuid import UUID

import logging

from ..schemas.label_patterns import PatternExtractionRequest
from ..schemas.labels import ApplyLabelRequest, ApplyLabelResponse
from ..schemas.oauth import GmailTokens
from .gmail_toolkit import GmailService
from .pattern_learning_service import PatternLearningService
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class LabelService:
    """Apply Gmail labels via Composio and persist state."""

    def __init__(
        self,
        gmail_service: GmailService,
        supabase: SupabaseService,
        pattern_service: PatternLearningService | None = None,
    ) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase
        self._pattern_service = pattern_service or PatternLearningService(supabase)

    async def apply_label(self, request: ApplyLabelRequest) -> ApplyLabelResponse:
        tokens = await self._ensure_tokens(request.user_id)
        label_id = request.gmail_label_id or request.label_name
        await self._gmail_service.apply_label(
            message_id=request.gmail_message_id,
            label_id=label_id,
            tokens=tokens,
            user_id=str(request.user_id),
        )
        logger.info(
            "Applied Gmail label {} to message {} for user {}",
            label_id,
            request.gmail_message_id,
            request.user_id,
        )

        # Trigger pattern extraction asynchronously (don't block on failure)
        await self._extract_patterns_after_labeling(
            user_id=request.user_id,
            gmail_message_id=request.gmail_message_id,
            applied_label=request.label_name,
        )

        return ApplyLabelResponse(success=True, applied_label=label_id)

    async def _extract_patterns_after_labeling(
        self, user_id: UUID, gmail_message_id: str, applied_label: str
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
                    f"Email {gmail_message_id} not found in database. "
                    "Skipping pattern extraction."
                )
                return

            # Check if sender_email is available
            if not email.sender_email:
                logger.warning(
                    f"Sender email not available for email {email.id}. "
                    "Skipping pattern extraction."
                )
                return

            # Extract patterns from the labeled email
            extraction_request = PatternExtractionRequest(
                email_id=email.id,
                applied_label=applied_label,
                sender_email=email.sender_email,
                email_subject=email.subject or "",
                email_snippet=email.snippet,
            )

            await self._pattern_service.extract_and_store_patterns(
                request=extraction_request,
                user_id=user_id,
            )

            # Update email with applied label metadata
            domain = self._extract_domain(email.sender_email)
            await self._supabase.update_email_label(
                email_id=email.id,
                applied_label=applied_label,
                sender_domain=domain,
            )

            logger.info(f"Patterns extracted for email {email.id}")

        except Exception as e:
            # Don't fail the label application if pattern extraction fails
            logger.warning(f"Pattern extraction failed: {e}")

    def _extract_domain(self, email: str) -> str | None:
        """Extract domain from email address."""
        match = re.search(r"@([\w\.-]+)", email)
        if match:
            return match.group(1).lower()
        return None

    async def _ensure_tokens(self, user_id: UUID) -> GmailTokens:
        tokens = await self._supabase.fetch_gmail_tokens(user_id)
        if not tokens:
            raise ValueError("No Gmail tokens found for user. Complete onboarding first.")
        return tokens
