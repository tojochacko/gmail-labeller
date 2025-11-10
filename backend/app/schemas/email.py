"""Email schema definitions."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase."""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


# Type aliases for label-related fields
LabelType = Literal["Important", "Not Important"]
LabelSource = Literal["auto", "manual", "agent"]
UpdatedBy = Literal["auto", "user", "agent"]


class EmailItem(BaseModel):
    """Represents an email fetched from Gmail via Composio.

    Uses consolidated label system with metadata for auto-labeling:
    - label: 'Important', 'Not Important', or None
    - label_confidence: 0.0-1.0 confidence score
    - label_source: 'auto', 'manual', or 'agent'
    - labeled_at: timestamp when labeled
    - last_updated_by: 'auto', 'user', or 'agent'
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,  # Allow both snake_case and camelCase when parsing
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

    # ============================================
    # NEW: Consolidated Label System (Post-Migration)
    # ============================================
    label: Optional[LabelType] = Field(
        default=None,
        description="Consolidated label: 'Important', 'Not Important', or None for Uncategorized."
    )
    label_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) for auto-applied labels. Manual labels have 1.0."
    )
    label_source: Optional[LabelSource] = Field(
        default=None,
        description=(
            "Source of label: 'auto' (pattern-based), 'manual' (user-applied), "
            "or 'agent' (AI suggestion)."
        )
    )
    labeled_at: Optional[datetime] = Field(
        default=None, description="Timestamp when label was applied or last updated."
    )
    last_updated_by: Optional[UpdatedBy] = Field(
        default=None,
        description="Last entity that updated the label: 'auto', 'user', or 'agent'."
    )



class EmailStats(BaseModel):
    """Email categorization statistics."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    total: int = Field(..., description="Total number of emails")
    important: int = Field(..., description="Number of emails labeled Important")
    not_important: int = Field(..., description="Number of emails labeled Not Important")
    uncategorized: int = Field(..., description="Number of uncategorized emails (no label)")
    auto_labeled: int = Field(..., description="Number of auto-labeled emails")
    manual_labeled: int = Field(..., description="Number of manually labeled emails")


class EmailListResponse(BaseModel):
    """Response payload for GET /api/emails."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[EmailItem]


class EmailListResponseWithStats(BaseModel):
    """Enhanced response payload with categorization statistics."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    items: list[EmailItem]
    stats: EmailStats
