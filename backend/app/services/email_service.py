"""Email orchestration service with auto-labeling support."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Sequence
from uuid import UUID, uuid4

import logging

from ..config import Settings
from ..schemas.email import EmailItem
from ..schemas.oauth import GmailTokens
from .auto_label_engine import AutoLabelEngine
from .gmail_toolkit import GmailService
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class EmailService:
    """Fetch and persist Gmail messages for a given user with intelligent auto-labeling."""

    def __init__(
        self,
        gmail_service: GmailService,
        supabase: SupabaseService,
        settings: Settings | None = None,
        auto_label_engine: AutoLabelEngine | None = None,
    ) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase
        self._settings = settings
        self._auto_label_engine = auto_label_engine or AutoLabelEngine(supabase)

    def _llm_absent(self) -> bool:
        """Return True when no LLM backend is configured."""
        if self._settings is None:
            return True
        return (
            self._settings.agent_runtime_base_url is None
            and not self._settings.ollama_enabled
        )

    async def fetch_latest_emails(
        self, user_id: UUID, max_results: int = 20, query: str | None = None
    ) -> list[EmailItem]:
        """Fetch latest emails from Gmail and sync with database.

        NEW (2025-11-09): Now includes intelligent auto-labeling for new emails!
        - Auto-applies labels based on learned patterns (confidence >= 40%)
        - Preserves existing labels when re-fetching (never overwrites manual labels)
        - Updates Gmail with "AI:Important" or "AI:Not Important" labels
        """
        logger.info(f"🔄 FETCH START: user={user_id}, max_results={max_results}, query={query}")
        tokens = await self._ensure_tokens(user_id)
        messages = await self._gmail_service.list_messages(
            tokens=tokens,
            user_id=str(user_id),
            max_results=max_results,
            query=query,
        )
        logger.info(f"📧 Fetched {len(messages)} Gmail messages for user {user_id}")

        if len(messages) == 0:
            logger.warning(f"No messages returned from Gmail for user {user_id}")
        else:
            logger.debug(f"First message sample: {messages[0] if messages else None}")

        items: list[EmailItem] = []
        new_count = 0
        existing_count = 0
        auto_labeled_count = 0

        for raw in messages:
            item = self._parse_email(raw)

            # Check if email already exists and reuse ID + preserve fields
            existing = await self._supabase.fetch_email_by_gmail_id(user_id, item.gmail_message_id)

            if existing:
                # ============================================
                # EXISTING EMAIL: Preserve all fields
                # ============================================
                existing_count += 1
                item.id = existing.id
                logger.debug(f"Reusing existing email ID {existing.id} for {item.gmail_message_id}")

                # Preserve consolidated label fields
                if existing.label:
                    item.label = existing.label
                    item.label_confidence = existing.label_confidence
                    item.label_source = existing.label_source
                    item.labeled_at = existing.labeled_at
                    item.last_updated_by = existing.last_updated_by
                    confidence_display = (
                        f"{existing.label_confidence:.2f}"
                        if existing.label_confidence is not None
                        else "N/A"
                    )
                    logger.debug(
                        f"Preserved label '{existing.label}' "
                        f"(source: {existing.label_source}, "
                        f"confidence: {confidence_display})"
                    )

                # Preserve sender_domain if it was already extracted
                if existing.sender_domain and not item.sender_domain:
                    item.sender_domain = existing.sender_domain

            else:
                # ============================================
                # NEW EMAIL: Apply auto-labeling
                # ============================================
                new_count += 1
                logger.info(
                    f"🆕 NEW EMAIL: {item.gmail_message_id} - '{item.subject[:50]}...' "
                    f"from {item.sender_email}"
                )

                # Try auto-labeling for new emails only when LLM is not configured
                try:
                    suggestion = (
                        await self._auto_label_engine.suggest_label(
                            email=item,
                            user_id=user_id,
                        )
                        if self._llm_absent()
                        else None
                    )

                    if suggestion:
                        # Auto-label confidence >= threshold!
                        auto_labeled_count += 1
                        item.label = suggestion.label
                        item.label_confidence = suggestion.confidence
                        item.label_source = "auto"
                        item.labeled_at = datetime.now(timezone.utc)
                        item.last_updated_by = "auto"

                        logger.info(
                            f"🤖 AUTO-LABELED: '{item.label}' "
                            f"(confidence: {suggestion.confidence:.3f}, "
                            f"matched: {', '.join(suggestion.matched_patterns)})"
                        )

                        # Apply label to Gmail
                        try:
                            await self._gmail_service.apply_label(
                                message_id=item.gmail_message_id,
                                label_id=item.label,  # "Important" or "Not Important"
                                tokens=tokens,
                                user_id=str(user_id),
                            )
                            logger.debug(f"✅ Applied '{item.label}' to Gmail")
                        except Exception as e:
                            logger.warning(f"Failed to apply label to Gmail (continuing): {e}")
                    else:
                        # Confidence below threshold - email remains Uncategorized
                        logger.debug(
                            f"📭 UNCATEGORIZED: Email '{item.subject[:50]}...' "
                            f"(no pattern match or low confidence)"
                        )

                except Exception as e:
                    logger.error(f"Auto-labeling failed for {item.gmail_message_id}: {e}")
                    # Continue without auto-label on error

            await self._supabase.upsert_email(user_id, item)
            items.append(item)

        logger.info(
            f"✅ FETCH COMPLETE: {len(items)} emails "
            f"({new_count} new, {existing_count} existing, "
            f"{auto_labeled_count} auto-labeled)"
        )
        return items

    async def _ensure_tokens(self, user_id: UUID) -> GmailTokens:
        tokens = await self._supabase.fetch_gmail_tokens(user_id)
        if not tokens:
            raise ValueError("No Gmail tokens found for user. Complete onboarding first.")
        return tokens

    def _parse_email(self, message: dict) -> EmailItem:
        """Parse Gmail message into EmailItem.

        Extracts all fields including sender information for proper database storage.
        """
        # Log raw message structure for debugging
        logger.debug(f"Parsing email with keys: {list(message.keys())}")

        # Composio returns simplified format with subject at top level
        # Check both formats: raw Gmail API vs Composio simplified
        if "subject" in message:
            # Composio format: subject at top level
            subject = message.get("subject", "(no subject)")
            received_at = message.get("received_at") or datetime.now(timezone.utc)
            if isinstance(received_at, str):
                from email.utils import parsedate_to_datetime

                try:
                    received_at = parsedate_to_datetime(received_at)
                except (ValueError, TypeError):
                    received_at = datetime.now(timezone.utc)

            # Extract sender from Composio format
            sender_email = message.get("sender") or message.get("from")
        else:
            # Raw Gmail API format: subject in headers
            headers = self._normalize_headers(message.get("payload", {}).get("headers", []))
            subject = headers.get("subject", "(no subject)")
            received_at = self._extract_received_at(headers) or datetime.now(timezone.utc)

            # Extract sender from headers
            sender_email = headers.get("from")

        # Extract domain from sender email
        sender_domain = None
        if sender_email:
            import re

            match = re.search(r"@([\w\.-]+)", sender_email)
            if match:
                sender_domain = match.group(1).lower()
                logger.debug(f"Extracted domain '{sender_domain}' from sender '{sender_email}'")

        email_id = uuid4()

        # Try multiple field names for Gmail message ID
        gmail_msg_id = (
            message.get("id")  # Raw Gmail API
            or message.get("message_id")  # Composio might use this
            or message.get("messageId")  # camelCase variant
            or str(email_id)  # Fallback to UUID
        )

        if gmail_msg_id == str(email_id):
            logger.warning(
                f"Gmail message ID not found in message! Keys: {list(message.keys())}. "
                f"Using UUID fallback: {email_id}"
            )

        return EmailItem(
            id=email_id,
            gmail_message_id=gmail_msg_id,
            thread_id=message.get("threadId", message.get("thread_id", "")),
            subject=subject,
            snippet=message.get("snippet"),
            sender_email=sender_email,
            sender_domain=sender_domain,
            received_at=received_at,
            processed_at=None,
            # Consolidated label fields - will be set by auto-labeling engine
            label=None,
            label_confidence=None,
            label_source=None,
            labeled_at=None,
            last_updated_by=None,
        )

    def _normalize_headers(self, headers: Sequence[dict]) -> dict[str, str]:
        result: dict[str, str] = {}
        for header in headers:
            name = header.get("name")
            value = header.get("value")
            if isinstance(name, str) and isinstance(value, str):
                result[name.lower()] = value
        return result

    def _extract_received_at(self, headers: dict[str, str]) -> datetime | None:
        for key in ("date", "received"):
            raw_value = headers.get(key)
            if not raw_value:
                continue
            try:
                return parsedate_to_datetime(raw_value)
            except (ValueError, TypeError):
                continue
        return None
