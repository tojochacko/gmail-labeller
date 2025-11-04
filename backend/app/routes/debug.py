"""Debug routes for troubleshooting."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ..dependencies import get_supabase_service
from ..services.supabase_service import SupabaseService

router = APIRouter()


@router.get("/emails/{user_id}")
async def debug_emails(
    user_id: UUID,
    supabase: SupabaseService = Depends(get_supabase_service),
) -> dict:
    """Debug endpoint to see raw email data from database."""
    import asyncio

    def fetch_all_emails(uid: str):
        query = supabase.client.table("emails").select("*").eq("user_id", uid)
        response = query.execute()
        return response.data or []

    emails = await asyncio.to_thread(fetch_all_emails, str(user_id))
    return {
        "count": len(emails),
        "emails": emails,
    }


@router.get("/agent-runs/{user_id}")
async def debug_agent_runs(
    user_id: UUID,
    supabase: SupabaseService = Depends(get_supabase_service),
) -> dict:
    """Debug endpoint to see raw agent run data from database."""
    import asyncio

    def fetch_all_runs(uid: str):
        query = supabase.client.table("agent_runs").select("*").eq("user_id", uid)
        response = query.execute()
        return response.data or []

    runs = await asyncio.to_thread(fetch_all_runs, str(user_id))
    return {
        "count": len(runs),
        "runs": runs,
    }
