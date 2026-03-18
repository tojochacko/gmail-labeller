"""Classification session lifecycle management."""

from __future__ import annotations

import logging
from uuid import UUID

from ..schemas.email import EmailItem
from .email_service import EmailService
from .session_repository import SessionRepository

logger = logging.getLogger(__name__)

# Only fetch emails that have not yet been classified by AI
UNLABELED_QUERY = 'in:inbox -label:"TImportant" -label:"TNotImportant"'


class ClassificationSessionService:
    """Manage the lifecycle of a classification session (create, fetch, cleanup)."""

    def __init__(self, session_repo: SessionRepository, email_service: EmailService) -> None:
        self._repo = session_repo
        self._email_service = email_service

    async def create_session(
        self, user_id: UUID, max_results: int = 10
    ) -> tuple[UUID, list[EmailItem]]:
        """Create a session, fetch unlabeled emails into it, and return session ID + emails.

        Returns emails with live gmail_labels populated so callers can display them
        without a round-trip to the DB (where gmail_labels is not persisted).

        Only fetches emails without TImportant or TNotImportant labels applied.

        Args:
            user_id: User UUID
            max_results: Max emails to fetch

        Returns:
            Tuple of (session UUID, list of EmailItem with live gmail_labels)
        """
        session_id = await self._repo.create_session(user_id)
        logger.info("Created classification session %s for user %s", session_id, user_id)
        logger.info("Fetching unclassified emails with query: %s", UNLABELED_QUERY)

        emails = await self._email_service.fetch_latest_emails(
            user_id=user_id,
            max_results=max_results,
            query=UNLABELED_QUERY,
        )

        for email in emails:
            await self._repo.set_email_session(email.id, session_id)

        await self._repo.update_session_status(
            session_id, status="pending", email_count=len(emails)
        )
        logger.info("Session %s linked to %d emails", session_id, len(emails))
        return session_id, emails

    async def get_session_review_items(self, session_id: UUID) -> list[dict]:
        """Return emails paired with their AI suggestion from agent_runs.

        Used by the review UI so it can display what label the AI applied
        without reading label fields from the emails table.
        """
        emails = await self.get_session_emails(session_id)
        runs = await self._repo.fetch_session_agent_runs(session_id)
        suggestion_map = {
            r["email_id"]: r.get("result_payload") or {} for r in runs
        }
        return [
            {
                "email": e,
                "suggestion": suggestion_map.get(str(e.id), {}).get("suggestion"),
                "confidence": suggestion_map.get(str(e.id), {}).get("confidence"),
            }
            for e in emails
        ]

    async def get_session(self, session_id: UUID) -> dict | None:
        """Fetch session metadata by ID."""
        return await self._repo.fetch_session(session_id)

    async def get_session_emails(self, session_id: UUID) -> list[EmailItem]:
        """Fetch all emails in a session as EmailItem objects."""
        rows = await self._repo.fetch_session_emails(session_id)
        items: list[EmailItem] = []
        for row in rows:
            try:
                items.append(EmailItem(**row))
            except Exception as e:
                logger.warning("Failed to parse email row %s: %s", row.get("id"), e)
        return items

    async def cleanup_session(self, session_id: UUID) -> dict:
        """Delete emails and agent_runs for a session, mark it cleaned_up.

        The label_patterns table is never touched (it stores learned knowledge).

        Args:
            session_id: Session UUID

        Returns:
            Dict with emails_deleted and runs_deleted counts
        """
        emails_deleted = await self._repo.delete_session_emails(session_id)
        runs_deleted = await self._repo.delete_session_agent_runs(session_id)
        await self._repo.update_session_status(session_id, status="cleaned_up")
        logger.info(
            "Session %s cleaned up: %d emails, %d runs deleted",
            session_id,
            emails_deleted,
            runs_deleted,
        )
        return {"emails_deleted": emails_deleted, "runs_deleted": runs_deleted}
