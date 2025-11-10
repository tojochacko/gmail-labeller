"""Label application service with auto-labeling and pattern learning support."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID

import logging

from ..schemas.email import EmailItem, LabelType
from ..schemas.label_patterns import PatternExtractionRequest
from ..schemas.labels import ApplyLabelRequest, ApplyLabelResponse
from ..schemas.oauth import GmailTokens
from .auto_label_engine import AutoLabelEngine
from .gmail_toolkit import GmailService
from .pattern_learning_service import PatternLearningService
from .supabase_service import SupabaseService


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
        auto_label_engine: AutoLabelEngine | None = None,
    ) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase
        self._pattern_service = pattern_service or PatternLearningService(supabase)
        self._auto_label_engine = auto_label_engine or AutoLabelEngine(supabase)

    async def apply_label(self, request: ApplyLabelRequest) -> ApplyLabelResponse:
        """Apply a Gmail label and update database with re-mark detection.

        NEW (2025-11-09): Now detects re-marks and applies 2x weight learning!

        This method:
        1. Ensures the email exists in the database (fetches from Gmail if needed)
        2. Detects if this is a re-mark (changing existing label)
        3. Applies the label to Gmail via Composio
        4. Updates the label in the database with new consolidated schema
        5. If re-mark: triggers accelerated learning (2x pattern weight)
        6. Otherwise: triggers normal pattern extraction

        Args:
            request: Label application request with user_id, message_id, and label_name

        Returns:
            ApplyLabelResponse with success status and applied label

        Raises:
            ValueError: If user has no Gmail tokens or email cannot be processed
        """
        logger.info(
            f"🏷️  APPLY_LABEL START: user_id={request.user_id}, "
            f"gmail_message_id={request.gmail_message_id}, label_name={request.label_name}"
        )

        tokens = await self._ensure_tokens(request.user_id)
        label_id = request.gmail_label_id or request.label_name

        # CRITICAL: Ensure email exists in database before labeling
        # This fetches from Gmail if the email isn't in the database yet
        logger.debug(f"Checking if email {request.gmail_message_id} exists in database...")
        email = await self._ensure_email_in_database(
            user_id=request.user_id,
            gmail_message_id=request.gmail_message_id,
            tokens=tokens,
        )

        if not email:
            logger.error(
                f"❌ Failed to fetch/store email {request.gmail_message_id}. Cannot apply label."
            )
            # Still apply the label to Gmail, but warn about database sync
            logger.warning("⚠️  Applying label to Gmail only - database will not be updated")
        else:
            logger.info(
                f"✅ Email found in database: id={email.id}, subject={email.subject}, "
                f"sender_email={email.sender_email}"
            )

        # ============================================
        # NEW: Detect Re-Mark (label change)
        # ============================================
        is_remark = False
        old_label = None

        if email:
            old_label = email.label

            if old_label and old_label != request.label_name:
                is_remark = True
                logger.info(
                    f"📝 RE-MARK DETECTED: '{old_label}' → '{request.label_name}' "
                    f"(will apply 2x learning weight)"
                )
            elif old_label == request.label_name:
                logger.debug(f"Same label reapplied: '{request.label_name}' (no re-mark)")
            else:
                logger.debug(f"First-time label: '{request.label_name}' (no previous label)")

        # Apply label to Gmail
        logger.debug(f"Applying label '{label_id}' to Gmail message {request.gmail_message_id}...")
        await self._gmail_service.apply_label(
            message_id=request.gmail_message_id,
            label_id=label_id,
            tokens=tokens,
            user_id=str(request.user_id),
        )
        logger.info(f"✅ Gmail label '{label_id}' applied successfully")

        # ============================================
        # NEW: Update database with consolidated schema
        # ============================================
        if email:
            domain = self._extract_domain(email.sender_email) if email.sender_email else None
            logger.info(
                f"📝 Updating database with NEW SCHEMA: email_id={email.id}, "
                f"label={request.label_name}, source=manual, confidence=1.0"
            )

            try:
                # Use new consolidated schema update method
                await self._supabase.update_email_with_new_schema(
                    email_id=email.id,
                    label=request.label_name,
                    label_confidence=1.0,  # Manual labels = 100% confidence
                    label_source="manual",
                    labeled_at=datetime.now(timezone.utc),
                    last_updated_by="user",
                    sender_domain=domain,
                )
                logger.info(
                    f"✅ DATABASE UPDATE SUCCESS (new schema): email {email.id} "
                    f"labeled as '{request.label_name}'"
                )
            except Exception as e:
                logger.error(
                    f"❌ DATABASE UPDATE FAILED: email_id={email.id}, error={str(e)}",
                    exc_info=True
                )
                # Re-raise to let caller know database update failed
                raise

            # ============================================
            # NEW: Accelerated Learning for Re-Marks
            # ============================================
            if is_remark:
                logger.info(
                    f"🚀 ACCELERATED LEARNING: Applying 2x weight for re-mark "
                    f"'{old_label}' → '{request.label_name}'"
                )
                try:
                    # Update patterns with 2x weight for the NEW label
                    await self._auto_label_engine.update_pattern_on_remark(
                        email=email,
                        new_label=request.label_name,  # type: ignore
                        user_id=request.user_id,
                    )
                    logger.info(
                        f"✅ Re-mark learning complete: patterns updated with 2x weight"
                    )
                except Exception as e:
                    logger.warning(
                        f"⚠️  Re-mark learning failed (non-fatal): {str(e)}",
                        exc_info=True
                    )
            else:
                # Normal pattern extraction for first-time labels
                logger.debug("Starting pattern extraction (normal weight)...")
                try:
                    await self._extract_patterns_after_labeling(
                        user_id=request.user_id,
                        gmail_message_id=request.gmail_message_id,
                        applied_label=request.label_name,
                    )
                    logger.debug("✅ Pattern extraction completed")
                except Exception as e:
                    logger.warning(
                        f"⚠️  Pattern extraction failed (non-fatal): {str(e)}",
                        exc_info=True
                    )
        else:
            logger.warning(
                f"⚠️  Skipping database update - email {request.gmail_message_id} not in database"
            )

        logger.info(
            f"🏷️  APPLY_LABEL COMPLETE: label={label_id}, is_remark={is_remark}"
        )
        return ApplyLabelResponse(success=True, label=label_id)


    async def _ensure_email_in_database(
        self,
        user_id: UUID,
        gmail_message_id: str,
        tokens: GmailTokens,
    ) -> EmailItem | None:
        """
        Ensure email exists in database, fetch from Gmail if needed.

        Args:
            user_id: User UUID
            gmail_message_id: Gmail message ID
            tokens: Gmail OAuth tokens

        Returns:
            EmailItem if found/created, None if fetch fails
        """
        logger.debug(f"🔍 Checking database for email: {gmail_message_id}")

        # First, check if email already exists in database
        email = await self._supabase.fetch_email_by_gmail_id(
            user_id=user_id, gmail_message_id=gmail_message_id
        )

        if email:
            logger.info(
                f"✅ Email {gmail_message_id} found in database: id={email.id}, "
                f"subject='{email.subject}'"
            )
            return email

        # Email not in database, fetch from Gmail
        logger.warning(
            f"⚠️  Email {gmail_message_id} NOT in database. Attempting to fetch from Gmail..."
        )

        try:
            # Fetch email from Gmail using list_messages with specific message ID
            # Note: Gmail API doesn't have a direct "get message by ID" in Composio,
            # so we use list_messages as a workaround
            logger.debug("Fetching recent messages from Gmail to find the email...")
            messages = await self._gmail_service.list_messages(
                tokens=tokens,
                user_id=str(user_id),
                max_results=100,  # Fetch recent messages
                query="",  # No query filter
            )

            logger.debug(f"Fetched {len(messages)} messages from Gmail")

            # Find the specific message in the results
            message_data = None
            for msg in messages:
                if msg.get("id") == gmail_message_id or msg.get("gmail_message_id") == gmail_message_id:
                    message_data = msg
                    logger.debug(f"✅ Found message {gmail_message_id} in Gmail response")
                    break

            if not message_data:
                logger.error(
                    f"❌ Message {gmail_message_id} not found in Gmail API response. "
                    f"Searched {len(messages)} recent messages. "
                    f"Email may have been deleted or user may not have access."
                )
                return None

            # Convert Gmail message to EmailItem
            from uuid import uuid4
            from datetime import datetime, timezone

            logger.debug(f"Converting Gmail message to EmailItem: {message_data.keys()}")

            email_item = EmailItem(
                id=uuid4(),
                gmail_message_id=message_data.get("id", gmail_message_id),
                thread_id=message_data.get("thread_id", ""),
                subject=message_data.get("subject", ""),
                snippet=message_data.get("snippet"),
                sender_email=message_data.get("sender", message_data.get("from")),
                received_at=datetime.fromisoformat(
                    message_data.get("date", datetime.now(timezone.utc).isoformat())
                )
                if isinstance(message_data.get("date"), str)
                else message_data.get("received_at", datetime.now(timezone.utc)),
                processed_at=None,
                label=None,
                label_confidence=None,
                label_source=None,
                labeled_at=None,
                last_updated_by=None,
            )

            logger.info(
                f"📧 Created EmailItem: id={email_item.id}, subject='{email_item.subject}', "
                f"sender={email_item.sender_email}"
            )

            # Store in database
            logger.debug(f"Upserting email {email_item.id} to database...")
            await self._supabase.upsert_email(user_id=user_id, payload=email_item)
            logger.info(f"✅ Successfully stored email {gmail_message_id} in database with id={email_item.id}")

            return email_item

        except Exception as e:
            logger.error(
                f"❌ Error fetching/storing email {gmail_message_id}: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            return None

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
                    f"Email {gmail_message_id} not found in database. Skipping pattern extraction."
                )
                return

            # Check if sender_email is available
            if not email.sender_email:
                logger.warning(
                    f"Sender email not available for email {email.id}. Skipping pattern extraction."
                )
                return

            # Extract patterns from the labeled email
            extraction_request = PatternExtractionRequest(
                email_id=email.id,
                label=applied_label,
                sender_email=email.sender_email,
                email_subject=email.subject or "",
                email_snippet=email.snippet,
            )

            await self._pattern_service.extract_and_store_patterns(
                request=extraction_request,
                user_id=user_id,
            )

            # Update email with applied label using new consolidated schema
            domain = self._extract_domain(email.sender_email)
            from datetime import datetime, timezone
            await self._supabase.update_email_with_new_schema(
                email_id=email.id,
                label=applied_label,
                label_confidence=1.0,  # Manual labels have 100% confidence
                label_source="manual",
                labeled_at=datetime.now(timezone.utc),
                last_updated_by="user",
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
