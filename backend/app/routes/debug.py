"""Debug routes for troubleshooting — only active when ENVIRONMENT=development."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from ..config import Settings, get_settings
from ..dependencies import get_db_service
from ..db.models import AgentRun, Email
from ..services.db_service import DBService

router = APIRouter()


def _require_dev(settings: Settings = Depends(get_settings)) -> None:
    if settings.environment != "development":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Debug endpoints are only available in development.",
        )


@router.get("/emails/{user_id}", dependencies=[Depends(_require_dev)])
async def debug_emails(
    user_id: UUID,
    db: DBService = Depends(get_db_service),
) -> dict:
    """Debug endpoint to see raw email data from database."""
    async with db.session_factory() as session:
        stmt = select(Email).where(Email.user_id == str(user_id))
        result = await session.execute(stmt)
        emails = [
            {
                "id": obj.id,
                "gmail_message_id": obj.gmail_message_id,
                "subject": obj.subject,
                "sender_email": obj.sender_email,
                "received_at": obj.received_at,
            }
            for obj in result.scalars().all()
        ]
    return {"count": len(emails), "emails": emails}


@router.get("/agent-runs/{user_id}", dependencies=[Depends(_require_dev)])
async def debug_agent_runs(
    user_id: UUID,
    db: DBService = Depends(get_db_service),
) -> dict:
    """Debug endpoint to see raw agent run data from database."""
    async with db.session_factory() as session:
        stmt = select(AgentRun).where(AgentRun.user_id == str(user_id))
        result = await session.execute(stmt)
        runs = [
            {
                "id": obj.id,
                "email_id": obj.email_id,
                "status": obj.status,
                "result_payload": obj.result_payload,
                "updated_at": obj.updated_at,
            }
            for obj in result.scalars().all()
        ]
    return {"count": len(runs), "runs": runs}
