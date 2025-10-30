"""Pydantic schemas used by the backend API."""

from .agent import AgentRunRequest, AgentRunResponse, AgentRunStatusResponse
from .email import EmailItem, EmailListResponse
from .labels import ApplyLabelRequest, ApplyLabelResponse
from .oauth import (
    OAuthCallbackRequest,
    OAuthCallbackResponse,
    OAuthStartRequest,
    OAuthStartResponse,
    OAuthStatusResponse,
    GmailTokens,
)

__all__ = [
    "AgentRunRequest",
    "AgentRunResponse",
    "AgentRunStatusResponse",
    "EmailItem",
    "EmailListResponse",
    "ApplyLabelRequest",
    "ApplyLabelResponse",
    "OAuthStartRequest",
    "OAuthStartResponse",
    "OAuthCallbackRequest",
    "OAuthCallbackResponse",
    "OAuthStatusResponse",
    "GmailTokens",
]
