"""Agent runtime integration service."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import httpx
import logging

from ..config import Settings
from ..schemas.agent import AgentRunRequest, AgentRunResponse, AgentRunStatusResponse
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class AgentService:
    """Trigger and monitor agent runs via the existing runtime API."""

    def __init__(self, settings: Settings, supabase: SupabaseService) -> None:
        self._settings = settings
        self._supabase = supabase

    async def trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        payload = request.model_dump()
        logger.info("Triggering agent run for email {} user {}", request.email_id, request.user_id)
        async with httpx.AsyncClient(base_url=str(self._settings.agent_runtime_base_url)) as client:
            response = await client.post("/runs", json=payload, timeout=30)
            response.raise_for_status()
            data = response.json()

        run_id = UUID(data["run_id"])
        status = data.get("status", "queued")
        await self._supabase.record_agent_run(
            run_id=run_id,
            user_id=request.user_id,
            email_id=request.email_id,
            status=status,
            result_payload=data.get("result_payload"),
        )
        return AgentRunResponse(run_id=run_id, status=status)

    async def get_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        logger.debug("Fetching agent run {}", run_id)
        cached = await self._supabase.fetch_agent_run(run_id)
        if cached:
            return cached

        async with httpx.AsyncClient(base_url=str(self._settings.agent_runtime_base_url)) as client:
            response = await client.get(f"/runs/{run_id}", timeout=15)
            response.raise_for_status()
            data = response.json()

        status = data.get("status", "unknown")
        user_id_raw = data.get("user_id")
        email_id_raw = data.get("email_id")
        updated_at_raw = data.get("updated_at")

        if isinstance(user_id_raw, str) and isinstance(email_id_raw, str):
            await self._supabase.record_agent_run(
                run_id=run_id,
                user_id=UUID(user_id_raw),
                email_id=UUID(email_id_raw),
                status=status,
                result_payload=data.get("result_payload"),
                error_message=data.get("error_message"),
            )

        if isinstance(updated_at_raw, str):
            try:
                updated_at = datetime.fromisoformat(updated_at_raw)
            except ValueError:
                updated_at = datetime.now(timezone.utc)
        else:
            updated_at = datetime.now(timezone.utc)

        return AgentRunStatusResponse(
            run_id=run_id,
            status=status,
            result_payload=data.get("result_payload"),
            updated_at=updated_at,
            error_message=data.get("error_message"),
        )
