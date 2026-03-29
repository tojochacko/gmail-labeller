"""Label management schemas."""

from uuid import UUID

from pydantic import BaseModel, Field


class ApplyLabelRequest(BaseModel):
    """Request payload for labeling a Gmail message."""

    user_id: UUID | None = Field(default=None, description="Internal user identifier.")
    gmail_message_id: str = Field(..., description="Gmail message ID to label.")
    label_name: str = Field(..., description="Human readable label.")
    gmail_label_id: str | None = Field(
        default=None, description="Optional Gmail label ID if already known."
    )


class ApplyLabelResponse(BaseModel):
    """Response payload for label application results."""

    success: bool
    label: str
