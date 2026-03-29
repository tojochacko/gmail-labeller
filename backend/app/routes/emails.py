"""Email routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ..dependencies import get_current_user, get_email_service
from ..schemas.email import EmailListResponse
from ..services.email_service import EmailService

router = APIRouter()


@router.get("", status_code=status.HTTP_200_OK)
async def list_emails(
    max_results: int = Query(20, ge=1, le=50),
    query: str | None = Query(
        None,
        description="Gmail search query (e.g., 'in:inbox', 'is:unread'). Defaults to 'in:inbox'",
    ),
    user_id: UUID = Depends(get_current_user),
    email_service: EmailService = Depends(get_email_service),
) -> JSONResponse:
    """Fetch latest Gmail messages for the authenticated user."""
    try:
        emails = await email_service.fetch_latest_emails(
            user_id=user_id, max_results=max_results, query=query
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    response_model = EmailListResponse(items=emails)
    return JSONResponse(
        content=response_model.model_dump(mode="json", by_alias=True),
        status_code=status.HTTP_200_OK,
    )
