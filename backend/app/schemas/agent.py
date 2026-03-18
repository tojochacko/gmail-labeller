"""Agent runtime schemas."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AgentRunRequest(BaseModel):
    """Trigger an agent workflow for a Gmail email."""

    user_id: UUID
    email_id: UUID
    gmail_message_id: str
    prompt: Optional[str] = Field(
        default=None, description="Optional override prompt for the agent run."
    )
    batch_run_id: Optional[UUID] = Field(
        default=None, description="Session ID when triggered as part of a batch classification."
    )


class AgentRunResponse(BaseModel):
    """Initial response after starting an agent run."""

    run_id: UUID
    status: str = "queued"


class AgentRunStatusResponse(BaseModel):
    """Polled status for an agent run."""

    run_id: UUID
    status: str
    result_payload: Optional[dict] = None
    updated_at: datetime
    error_message: Optional[str] = None
