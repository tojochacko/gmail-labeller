"""Label application service."""

from __future__ import annotations

from uuid import UUID

import logging

from ..schemas.labels import ApplyLabelRequest, ApplyLabelResponse
from ..schemas.oauth import GmailTokens
from .gmail_toolkit import GmailService
from .supabase_service import SupabaseService


logger = logging.getLogger(__name__)


class LabelService:
    """Apply Gmail labels via Composio and persist state."""

    def __init__(self, gmail_service: GmailService, supabase: SupabaseService) -> None:
        self._gmail_service = gmail_service
        self._supabase = supabase

    async def apply_label(self, request: ApplyLabelRequest) -> ApplyLabelResponse:
        tokens = await self._ensure_tokens(request.user_id)
        label_id = request.gmail_label_id or request.label_name
        await self._gmail_service.apply_label(
            message_id=request.gmail_message_id,
            label_id=label_id,
            tokens=tokens,
            user_id=str(request.user_id),
        )
        logger.info(
            "Applied Gmail label {} to message {} for user {}",
            label_id,
            request.gmail_message_id,
            request.user_id,
        )
        return ApplyLabelResponse(success=True, applied_label=label_id)

    async def _ensure_tokens(self, user_id: UUID) -> GmailTokens:
        tokens = await self._supabase.fetch_gmail_tokens(user_id)
        if not tokens:
            raise ValueError("No Gmail tokens found for user. Complete onboarding first.")
        return tokens
