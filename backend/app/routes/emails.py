"""Email routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import get_email_service
from ..schemas import EmailListResponse
from ..services.email_service import EmailService

router = APIRouter()


@router.get(
    "",
    response_model=EmailListResponse,
    status_code=status.HTTP_200_OK,
)
async def list_emails(
    user_id: UUID = Query(..., description="Internal user identifier"),
    max_results: int = Query(20, ge=1, le=50),
    query: str | None = Query(
        None,
        description="Gmail search query (e.g., 'in:inbox', 'is:unread', or empty for all). Defaults to 'in:inbox'",
    ),
    email_service: EmailService = Depends(get_email_service),
) -> EmailListResponse:
    """Fetch latest Gmail messages for the authenticated user."""
    try:
        emails = await email_service.fetch_latest_emails(
            user_id=user_id, max_results=max_results, query=query
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return EmailListResponse(items=emails)
