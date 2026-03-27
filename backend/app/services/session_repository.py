"""Database operations for classification sessions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import AgentRun, ClassificationSession, Email

logger = logging.getLogger(__name__)


class SessionRepository:
    """SQLAlchemy data access for classification_sessions, plus session-scoped email/run ops."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def create_session(self, user_id: UUID) -> UUID:
        """Create a new classification session and return its ID."""
        session_id = uuid4()
        async with self._session_factory() as session:
            session.add(
                ClassificationSession(
                    id=str(session_id),
                    user_id=str(user_id),
                    status="pending",
                )
            )
            await session.commit()
        return session_id

    async def update_session_status(
        self,
        session_id: UUID,
        status: str,
        email_count: int | None = None,
    ) -> None:
        """Update session status and optionally email_count."""
        updates: dict[str, Any] = {"status": status}
        if email_count is not None:
            updates["email_count"] = email_count
        if status in ("completed", "cleaned_up"):
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()
        async with self._session_factory() as session:
            stmt = (
                update(ClassificationSession)
                .where(ClassificationSession.id == str(session_id))
                .values(**updates)
            )
            await session.execute(stmt)
            await session.commit()

    async def fetch_session(self, session_id: UUID) -> dict | None:
        """Fetch a classification session by ID."""
        try:
            async with self._session_factory() as session:
                obj = await session.get(ClassificationSession, str(session_id))
                if obj is None:
                    return None
                return {
                    "id": obj.id,
                    "user_id": obj.user_id,
                    "status": obj.status,
                    "email_count": obj.email_count,
                    "completed_at": obj.completed_at,
                    "created_at": obj.created_at,
                }
        except Exception as e:
            logger.error("Error fetching session %s: %s", session_id, e)
            return None

    async def fetch_session_agent_runs(self, session_id: UUID) -> list[dict]:
        """Fetch agent run results for all emails in a session."""
        try:
            async with self._session_factory() as session:
                stmt = select(AgentRun.email_id, AgentRun.result_payload).where(
                    AgentRun.batch_run_id == str(session_id)
                )
                result = await session.execute(stmt)
                return [
                    {"email_id": row.email_id, "result_payload": row.result_payload}
                    for row in result.all()
                ]
        except Exception as e:
            logger.error("Error fetching session agent runs: %s", e)
            return []

    async def fetch_session_emails(self, session_id: UUID) -> list[dict]:
        """Fetch all emails in a session (any label status)."""
        try:
            async with self._session_factory() as session:
                stmt = (
                    select(Email)
                    .where(Email.session_id == str(session_id))
                    .order_by(Email.received_at.desc())
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()
                return [
                    {
                        "id": obj.id,
                        "user_id": obj.user_id,
                        "gmail_message_id": obj.gmail_message_id,
                        "thread_id": obj.thread_id,
                        "subject": obj.subject,
                        "snippet": obj.snippet,
                        "sender_email": obj.sender_email,
                        "sender_domain": obj.sender_domain,
                        "received_at": obj.received_at,
                        "session_id": obj.session_id,
                    }
                    for obj in rows
                ]
        except Exception as e:
            logger.error("Error fetching session emails: %s", e)
            return []

    async def set_email_session(self, email_id: UUID, session_id: UUID) -> None:
        """Link an email to a classification session."""
        async with self._session_factory() as session:
            stmt = (
                update(Email)
                .where(Email.id == str(email_id))
                .values(session_id=str(session_id))
            )
            await session.execute(stmt)
            await session.commit()

    async def delete_session_emails(self, session_id: UUID) -> int:
        """Delete all emails belonging to a session. Returns count deleted."""
        try:
            async with self._session_factory() as session:
                # Count first
                count_stmt = select(Email).where(Email.session_id == str(session_id))
                result = await session.execute(count_stmt)
                count = len(result.scalars().all())
                stmt = delete(Email).where(Email.session_id == str(session_id))
                await session.execute(stmt)
                await session.commit()
                return count
        except Exception as e:
            logger.error("Error deleting session emails: %s", e)
            raise

    async def delete_session_agent_runs(self, session_id: UUID) -> int:
        """Delete all agent_runs for a session batch. Returns count deleted."""
        try:
            async with self._session_factory() as session:
                count_stmt = select(AgentRun).where(AgentRun.batch_run_id == str(session_id))
                result = await session.execute(count_stmt)
                count = len(result.scalars().all())
                stmt = delete(AgentRun).where(AgentRun.batch_run_id == str(session_id))
                await session.execute(stmt)
                await session.commit()
                return count
        except Exception as e:
            logger.error("Error deleting session agent runs: %s", e)
            raise
