"""Email orchestration service."""

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

    def __init__(self, gmail_service: GmailService, supabase: SupabaseService) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase

    async def fetch_latest_emails(
        self, user_id: UUID, max_results: int = 20, query: str | None = None
    ) -> list[EmailItem]:
        logger.info(f"Fetching emails for user {user_id}, max_results={max_results}, query={query}")
        tokens = await self._ensure_tokens(user_id)
        messages = await self._gmail_service.list_messages(
            tokens=tokens,
            user_id=str(user_id),
            max_results=max_results,
            query=query,
        )
        logger.info(f"Fetched {len(messages)} Gmail messages for user {user_id}")

        if len(messages) == 0:
            logger.warning(f"No messages returned from Gmail for user {user_id}")
        else:
            logger.debug(f"First message sample: {messages[0] if messages else None}")

        items: list[EmailItem] = []
        for raw in messages:
            item = self._parse_email(raw)
            await self._supabase.upsert_email(user_id, item)
            items.append(item)

        logger.info(f"Returning {len(items)} parsed email items")
        return items

    async def _ensure_tokens(self, user_id: UUID) -> GmailTokens:
        tokens = await self._supabase.fetch_gmail_tokens(user_id)
        if not tokens:
            raise ValueError("No Gmail tokens found for user. Complete onboarding first.")
        return tokens

    def _parse_email(self, message: dict) -> EmailItem:
        headers = self._normalize_headers(message.get("payload", {}).get("headers", []))
        subject = headers.get("subject", "(no subject)")
        received_at = self._extract_received_at(headers) or datetime.now(timezone.utc)
        email_id = uuid4()
        return EmailItem(
            id=email_id,
            gmail_message_id=message.get("id", str(email_id)),
            thread_id=message.get("threadId", message.get("thread_id", "")),
            subject=subject,
            snippet=message.get("snippet"),
            received_at=received_at,
            processed_at=None,
            agent_suggestion=None,
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
