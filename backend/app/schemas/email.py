"""Email schema definitions."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# Type aliases for label-related fields
LabelType = Literal["Important", "Not Important"]
LabelSource = Literal["auto", "manual", "agent"]
UpdatedBy = Literal["auto", "user", "agent"]


class EmailItem(BaseModel):
    """Represents an email fetched from Gmail via Composio.

    Schema Migration (2025-11-09):
    - Consolidated label system from agent_suggestion + applied_label into single label field
    - Added metadata fields for auto-labeling: confidence, source, labeled_at, last_updated_by
    - Old fields marked as deprecated, will be removed after migration verification
    """

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

    # ============================================
    # DEPRECATED: Old Label Fields (Pre-Migration)
    # Will be removed after migration verification
    # ============================================
    agent_suggestion: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Use 'label' field. Latest agent-generated recommendation."
    )
    applied_label: Optional[str] = Field(
        default=None,
        description="[DEPRECATED] Use 'label' field. User-applied label: Important or Not Important."
    )
    label_applied_at: Optional[datetime] = Field(
        default=None,
        description="[DEPRECATED] Use 'labeled_at' field. Timestamp when label was applied."
    )


class EmailStats(BaseModel):
    """Email categorization statistics."""

    total: int = Field(..., description="Total number of emails")
    important: int = Field(..., description="Number of emails labeled Important")
    not_important: int = Field(..., description="Number of emails labeled Not Important")
    uncategorized: int = Field(..., description="Number of uncategorized emails (no label)")
    auto_labeled: int = Field(..., description="Number of auto-labeled emails")
    manual_labeled: int = Field(..., description="Number of manually labeled emails")


class EmailListResponse(BaseModel):
    """Response payload for GET /api/emails."""

    items: list[EmailItem]


class EmailListResponseWithStats(BaseModel):
    """Enhanced response payload with categorization statistics."""

    items: list[EmailItem]
    stats: EmailStats
