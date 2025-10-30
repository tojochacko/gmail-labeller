"""FastAPI dependency providers."""

from __future__ import annotations

from fastapi import Depends

from .config import Settings, get_settings
from .services import (
    AgentService,
    EmailService,
    GmailService,
    GmailToolkitFactory,
    LabelService,
    SupabaseService,
)

_supabase_service: SupabaseService | None = None
_gmail_service: GmailService | None = None


def get_supabase_service(settings: Settings = Depends(get_settings)) -> SupabaseService:
    global _supabase_service
    if _supabase_service is None:
        _supabase_service = SupabaseService(settings)
    return _supabase_service


def get_gmail_service(settings: Settings = Depends(get_settings)) -> GmailService:
    global _gmail_service
    if _gmail_service is None:
        toolkit = GmailToolkitFactory(settings).build()
        _gmail_service = GmailService(toolkit, settings)
    return _gmail_service


def get_email_service(
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: SupabaseService = Depends(get_supabase_service),
) -> EmailService:
    return EmailService(gmail_service, supabase)


def get_label_service(
    gmail_service: GmailService = Depends(get_gmail_service),
    supabase: SupabaseService = Depends(get_supabase_service),
) -> LabelService:
    return LabelService(gmail_service, supabase)


def get_agent_service(
    settings: Settings = Depends(get_settings),
    supabase: SupabaseService = Depends(get_supabase_service),
) -> AgentService:
    return AgentService(settings, supabase)
