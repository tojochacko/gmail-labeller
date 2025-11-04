"""Email schema definitions."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class EmailItem(BaseModel):
    """Represents an email fetched from Gmail via Composio."""

    id: UUID = Field(..., description="Internal UUID for Supabase record.")
    gmail_message_id: str = Field(..., description="Gmail message identifier.")
    thread_id: str = Field(..., description="Gmail thread identifier.")
    subject: str = Field(..., description="Email subject line.")
    snippet: Optional[str] = Field(default=None, description="Trimmed preview of the body.")
    sender_email: Optional[str] = Field(default=None, description="Email address of the sender.")
    received_at: datetime = Field(..., description="Timestamp from Gmail.")
    processed_at: Optional[datetime] = Field(
        default=None, description="Timestamp of the last agent processing run."
    )
    agent_suggestion: Optional[str] = Field(
        default=None, description="Latest agent-generated recommendation."
    )


class EmailListResponse(BaseModel):
    """Response payload for GET /api/emails."""

    items: list[EmailItem]
