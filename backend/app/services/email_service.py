"""Email fetch and persistence service."""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Sequence
from uuid import UUID, uuid4

import logging

from ..schemas.email import EmailItem
from ..schemas.oauth import GmailTokens
from .gmail_toolkit import GmailService
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class EmailService:
    """Fetch and persist Gmail messages for a given user."""

    def __init__(
        self,
        gmail_service: GmailService,
        supabase: SupabaseService,
        settings=None,
    ) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase

    async def fetch_latest_emails(
        self, user_id: UUID, max_results: int = 20, query: str | None = None
    ) -> list[EmailItem]:
        """Fetch latest emails from Gmail and sync with database.

        Emails with attachments are excluded at the Gmail query level using
        the `-has:attachment` operator so they never enter the classification pipeline.
        """
        # Always exclude attachment emails — they are sensitive and must not be sent
        # to a cloud LLM. The exclusion happens server-side in Gmail before any data
        # is transmitted, making this more efficient than post-fetch filtering.
        effective_query = f"{query} -has:attachment" if query else "in:inbox -has:attachment"

        logger.info(f"🔄 FETCH START: user={user_id}, max_results={max_results}, query={effective_query}")
        tokens = await self._ensure_tokens(user_id)
        messages = await self._gmail_service.list_messages(
            tokens=tokens,
            user_id=str(user_id),
            max_results=max_results,
            query=effective_query,
        )
        logger.info(f"📧 Fetched {len(messages)} Gmail messages for user {user_id}")

        items: list[EmailItem] = []
        new_count = 0
        existing_count = 0

        for raw in messages:
            item = self._parse_email(raw)

            existing = await self._supabase.fetch_email_by_gmail_id(user_id, item.gmail_message_id)
            if existing:
                existing_count += 1
                item.id = existing.id
                if existing.sender_domain and not item.sender_domain:
                    item.sender_domain = existing.sender_domain
            else:
                new_count += 1

            await self._supabase.upsert_email(user_id, item)
            items.append(item)

        items.sort(key=lambda e: e.received_at, reverse=True)
        logger.info(
            f"✅ FETCH COMPLETE: {len(items)} emails ({new_count} new, {existing_count} existing)"
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

        gmail_labels = (
            message.get("labelIds")
            or message.get("label_ids")
            or message.get("labels")
            or None
        )
        if isinstance(gmail_labels, list):
            gmail_labels = [str(lbl) for lbl in gmail_labels] or None

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
            gmail_labels=gmail_labels,
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
