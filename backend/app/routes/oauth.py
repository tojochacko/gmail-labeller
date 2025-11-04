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
    authorization_url = await gmail_service.create_authorization_url(
        state=state, user_id=str(payload.user_id)
    )
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
    # Handle Composio-managed OAuth flow
    if payload.connected_account_id and payload.status:
        if payload.status != "success":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"OAuth failed with status: {payload.status}",
            )

        # Store the connected account ID as the access token
        # Composio manages the actual OAuth tokens internally
        from ..schemas.oauth import GmailTokens
        from datetime import datetime, timezone, timedelta
        from pydantic import SecretStr

        tokens = GmailTokens(
            access_token=SecretStr(payload.connected_account_id),
            refresh_token=SecretStr("composio_managed"),
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=365),  # Long expiry for Composio-managed
            scope="gmail.modify",
            token_type="Bearer",
        )
        await supabase.store_gmail_tokens(payload.user_id, tokens)

        logger.info("Stored Composio-managed Gmail connection for user {}", payload.user_id)
        return OAuthCallbackResponse(connected=True, expires_at=tokens.expires_at)

    # Handle traditional OAuth2 flow
    if payload.code:
        tokens = await gmail_service.exchange_code_for_tokens(payload.code)
        await supabase.store_gmail_tokens(payload.user_id, tokens)

        logger.info("Stored Gmail OAuth tokens for user {}", payload.user_id)
        return OAuthCallbackResponse(connected=True, expires_at=tokens.expires_at)

    # Neither flow provided valid parameters
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Missing OAuth parameters. Provide either (code, state) or (connected_account_id, status).",
    )


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
