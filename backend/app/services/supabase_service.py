"""Supabase persistence helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import logging

from cryptography.fernet import Fernet
from pydantic import SecretStr
from supabase import Client, create_client

from ..config import Settings
from ..schemas.agent import AgentRunStatusResponse
from ..schemas.email import EmailItem
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)


class SupabaseService:
    """Lightweight wrapper around supabase-py with encryption support."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[Client] = None
        self._cipher = Fernet(settings.fernet_secret_key.get_secret_value().encode())

    @property
    def client(self) -> Client:
        if self._client is None:
            url = str(self._settings.supabase_url)
            service_key = self._settings.supabase_service_role_key.get_secret_value()
            self._client = create_client(url, service_key)
        return self._client

    async def upsert_user(self, user_id: UUID, email: str) -> None:
        payload = {
            "id": str(user_id),
            "email": email,
        }
        await self._execute("users", "upsert", payload)

    async def store_gmail_tokens(self, user_id: UUID, tokens: GmailTokens) -> None:
        payload = {
            "user_id": str(user_id),
            "access_token": self._encrypt(tokens.access_token.get_secret_value()),
            "refresh_token": self._encrypt(tokens.refresh_token.get_secret_value()),
            "expires_at": tokens.expires_at.isoformat(),
            "scope": tokens.scope,
            "token_type": tokens.token_type,
            "id_token": self._encrypt(tokens.id_token.get_secret_value())
            if tokens.id_token
            else None,
        }
        await self._execute("gmail_tokens", "upsert", payload)

    async def fetch_gmail_tokens(self, user_id: UUID) -> GmailTokens | None:
        result = await self._query("gmail_tokens", {"user_id": str(user_id)})
        if not result:
            return None
        row = result[0]
        expires_at = datetime.fromisoformat(row["expires_at"])
        return GmailTokens(
            access_token=SecretStr(self._decrypt(row["access_token"])),
            refresh_token=SecretStr(self._decrypt(row["refresh_token"])),
            expires_at=expires_at,
            scope=row.get("scope"),
            token_type=row.get("token_type", "Bearer"),
            id_token=SecretStr(self._decrypt(row["id_token"])) if row.get("id_token") else None,
        )

    async def upsert_email(self, user_id: UUID, payload: EmailItem) -> None:
        record = payload.model_dump()
        record["user_id"] = str(user_id)
        await self._execute("emails", "upsert", record)

    async def record_agent_run(
        self,
        run_id: UUID,
        user_id: UUID,
        email_id: UUID,
        status: str,
        result_payload: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> None:
        record = {
            "id": str(run_id),
            "user_id": str(user_id),
            "email_id": str(email_id),
            "status": status,
            "result_payload": result_payload,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._execute("agent_runs", "upsert", record)

    async def fetch_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        result = await self._query("agent_runs", {"id": str(run_id)})
        if not result:
            return None
        row = result[0]
        return AgentRunStatusResponse(
            run_id=UUID(row["id"]),
            status=row["status"],
            result_payload=row.get("result_payload"),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error_message=row.get("error_message"),
        )

    async def _execute(self, table: str, operation: str, payload: Any) -> None:
        logger.debug("Supabase {} on {} payload={}", operation, table, payload)
        await asyncio.to_thread(self._execute_sync, table, operation, payload)

    def _execute_sync(self, table: str, operation: str, payload: Any) -> None:
        query = self.client.table(table)
        if operation == "upsert":
            query = query.upsert(payload)
        else:  # pragma: no cover - defensive branch
            raise ValueError(f"Unsupported Supabase operation: {operation}")
        query.execute()

    async def _query(self, table: str, filters: dict[str, Any]) -> list[dict]:
        logger.debug("Supabase select on {} filters={}", table, filters)
        return await asyncio.to_thread(self._query_sync, table, filters)

    def _query_sync(self, table: str, filters: dict[str, Any]) -> list[dict]:
        query = self.client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        response = query.limit(1).execute()
        return response.data or []

    def _encrypt(self, plaintext: str) -> str:
        return self._cipher.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext.encode()).decode()
