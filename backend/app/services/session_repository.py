"""Database operations for classification sessions."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from supabase import Client


logger = logging.getLogger(__name__)


class SessionRepository:
    """Supabase data access for classification_sessions, plus session-scoped email/run ops."""

    def __init__(self, client: Client) -> None:
        self._client = client

    async def create_session(self, user_id: UUID) -> UUID:
        """Create a new classification session and return its ID."""
        session_id = await asyncio.to_thread(self._create_session_sync, str(user_id))
        return UUID(session_id)

    def _create_session_sync(self, user_id: str) -> str:
        response = (
            self._client.table("classification_sessions")
            .insert({"user_id": user_id, "status": "pending"})
            .execute()
        )
        return str(response.data[0]["id"])

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
        await asyncio.to_thread(self._update_session_sync, str(session_id), updates)

    def _update_session_sync(self, session_id: str, updates: dict) -> None:
        self._client.table("classification_sessions").update(updates).eq(
            "id", session_id
        ).execute()

    async def fetch_session(self, session_id: UUID) -> dict | None:
        """Fetch a classification session by ID."""
        try:
            result = await asyncio.to_thread(self._fetch_session_sync, str(session_id))
            return result[0] if result else None
        except Exception as e:
            logger.error("Error fetching session %s: %s", session_id, e)
            return None

    def _fetch_session_sync(self, session_id: str) -> list[dict]:
        response = (
            self._client.table("classification_sessions")
            .select("*")
            .eq("id", session_id)
            .limit(1)
            .execute()
        )
        return response.data or []

    async def fetch_session_agent_runs(self, session_id: UUID) -> list[dict]:
        """Fetch agent run results for all emails in a session."""
        try:
            return await asyncio.to_thread(
                self._fetch_session_agent_runs_sync, str(session_id)
            )
        except Exception as e:
            logger.error("Error fetching session agent runs: %s", e)
            return []

    def _fetch_session_agent_runs_sync(self, session_id: str) -> list[dict]:
        response = (
            self._client.table("agent_runs")
            .select("email_id,result_payload")
            .eq("batch_run_id", session_id)
            .execute()
        )
        return response.data or []

    async def fetch_session_emails(self, session_id: UUID) -> list[dict]:
        """Fetch all emails in a session (any label status)."""
        try:
            return await asyncio.to_thread(self._fetch_session_emails_sync, str(session_id))
        except Exception as e:
            logger.error("Error fetching session emails: %s", e)
            return []

    def _fetch_session_emails_sync(self, session_id: str) -> list[dict]:
        response = (
            self._client.table("emails")
            .select("*")
            .eq("session_id", session_id)
            .order("received_at", desc=True)
            .execute()
        )
        return response.data or []

    async def set_email_session(self, email_id: UUID, session_id: UUID) -> None:
        """Link an email to a classification session."""
        await asyncio.to_thread(
            lambda: self._client.table("emails")
            .update({"session_id": str(session_id)})
            .eq("id", str(email_id))
            .execute()
        )

    async def delete_session_emails(self, session_id: UUID) -> int:
        """Delete all emails belonging to a session. Returns count deleted."""
        try:
            return await asyncio.to_thread(
                self._delete_session_emails_sync, str(session_id)
            )
        except Exception as e:
            logger.error("Error deleting session emails: %s", e)
            raise

    def _delete_session_emails_sync(self, session_id: str) -> int:
        response = (
            self._client.table("emails").delete().eq("session_id", session_id).execute()
        )
        return len(response.data) if response.data else 0

    async def delete_session_agent_runs(self, session_id: UUID) -> int:
        """Delete all agent_runs for a session batch. Returns count deleted."""
        try:
            return await asyncio.to_thread(
                self._delete_session_agent_runs_sync, str(session_id)
            )
        except Exception as e:
            logger.error("Error deleting session agent runs: %s", e)
            raise

    def _delete_session_agent_runs_sync(self, session_id: str) -> int:
        response = (
            self._client.table("agent_runs")
            .delete()
            .eq("batch_run_id", session_id)
            .execute()
        )
        return len(response.data) if response.data else 0
