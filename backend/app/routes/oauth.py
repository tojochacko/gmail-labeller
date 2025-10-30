"""OAuth endpoints."""

from __future__ import annotations

import logging
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_gmail_service, get_supabase_service
from ..schemas.oauth import (
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthStatusResponse,
)
from ..services.gmail_toolkit import GmailService
from ..services.supabase_service import SupabaseService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/start", response_model=OAuthStartResponse, status_code=status.HTTP_200_OK)
async def start_oauth_flow(
    payload: OAuthStartRequest,
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: SupabaseService = Depends(get_supabase_service),
) -> OAuthStartResponse:
    """Kick off Gmail OAuth by returning an authorization URL."""
    state = secrets.token_urlsafe(16)
    await supabase.upsert_user(payload.user_id, payload.email)
    authorization_url = await gmail_service.create_authorization_url(state=state)
    logger.info("Generated Gmail OAuth URL for user {}", payload.user_id)
    return OAuthStartResponse(authorization_url=authorization_url, state=state)


@router.post(
    "/callback",
    response_model=OAuthCallbackResponse,
    status_code=status.HTTP_200_OK,
)
async def oauth_callback(
    payload: OAuthCallbackRequest,
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: SupabaseService = Depends(get_supabase_service),
) -> OAuthCallbackResponse:
    """Process Gmail OAuth callback and persist Supabase tokens."""
    tokens = await gmail_service.exchange_code_for_tokens(payload.code)
    await supabase.store_gmail_tokens(payload.user_id, tokens)

    logger.info("Stored Gmail OAuth tokens for user {}", payload.user_id)
    return OAuthCallbackResponse(connected=True, expires_at=tokens.expires_at)


@router.get(
    "/status/{user_id}",
    response_model=OAuthStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_oauth_status(
    user_id: UUID,
    supabase: SupabaseService = Depends(get_supabase_service),
) -> OAuthStatusResponse:
    """Return whether the user has an active Gmail connection."""
    tokens = await supabase.fetch_gmail_tokens(user_id)
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Gmail connection found for user.",
        )

    return OAuthStatusResponse(connected=True, expires_at=tokens.expires_at)
