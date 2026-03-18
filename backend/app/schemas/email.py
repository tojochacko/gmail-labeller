"""Email schema definitions."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


# Gmail is the single source of truth for labels.
LabelType = Literal["Important", "Not Important"]


class EmailItem(BaseModel):
    """Represents an email fetched from Gmail via Composio."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID = Field(..., description="Internal UUID for Supabase record.")
    gmail_message_id: str = Field(..., description="Gmail message identifier.")
    thread_id: str = Field(..., description="Gmail thread identifier.")
    subject: str = Field(..., description="Email subject line.")
    snippet: Optional[str] = Field(default=None, description="Trimmed preview of the body.")
    sender_email: Optional[str] = Field(default=None, description="Email address of the sender.")
    sender_domain: Optional[str] = Field(
        default=None, description="Domain extracted from sender email (e.g., gmail.com)."
    )
    received_at: datetime = Field(..., description="Timestamp from Gmail.")
    processed_at: Optional[datetime] = Field(
        default=None, description="Timestamp of the last agent processing run."
    )


class EmailListResponse(BaseModel):
    """Response payload for GET /api/emails."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[EmailItem]
