"""Label patterns schemas for AI learning."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LabelPatternBase(BaseModel):
    """Base schema for label patterns."""

    label_type: Literal["Important", "Not Important"] = Field(
        ..., description="Category this pattern belongs to"
    )
    pattern_type: Literal["domain", "keyword"] = Field(..., description="Type of pattern")
    pattern_value: str = Field(..., min_length=1, max_length=500, description="The pattern value")
    confidence_score: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score 0.0-1.0"
    )

    @field_validator("pattern_value")
    @classmethod
    def validate_pattern_value(cls, v: str) -> str:
        """Ensure pattern value is normalized."""
        return v.strip().lower()


class LabelPatternCreate(LabelPatternBase):
    """Schema for creating a new pattern (user-defined)."""

    pass


class LabelPatternUpdate(BaseModel):
    """Schema for updating a pattern."""

    confidence_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Updated confidence score"
    )
    pattern_value: Optional[str] = Field(
        None, min_length=1, max_length=500, description="Updated pattern value"
    )


class LabelPattern(LabelPatternBase):
    """Complete label pattern with database fields.

    Schema Migration (2025-11-09):
    - Added learning tracking fields for auto-labeling system
    - times_applied: tracks usage count for this pattern
    - times_corrected: tracks how often user re-marked emails matching this pattern
    - last_applied_at: last time pattern was used for auto-labeling
    - pattern_weight: multiplier for pattern importance (2.0 for re-marks, 1.0 default)
    """

    pattern_id: UUID
    user_id: UUID
    occurrence_count: int = Field(default=1)
    last_seen_at: datetime
    is_user_defined: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime

    # ============================================
    # NEW: Learning Tracking Fields (Post-Migration)
    # ============================================
    times_applied: int = Field(
        default=0, description="Number of times this pattern was used for auto-labeling"
    )
    times_corrected: int = Field(
        default=0, description="Number of times user corrected this pattern (re-marked)"
    )
    last_applied_at: Optional[datetime] = Field(
        default=None, description="Last time this pattern was used for labeling"
    )
    pattern_weight: float = Field(
        default=1.0,
        ge=0.0,
        le=5.0,
        description="Weight multiplier (1.0 default, 2.0 for re-marks, up to 5.0 max)",
    )

    model_config = ConfigDict(from_attributes=True)


class LabelPatternListResponse(BaseModel):
    """Response for listing label patterns."""

    patterns: list[LabelPattern]
    total: int


class LearnedContext(BaseModel):
    """Learned patterns formatted for AI prompt injection."""

    important_domains: list[str] = Field(default_factory=list)
    important_keywords: list[str] = Field(default_factory=list)
    not_important_domains: list[str] = Field(default_factory=list)
    not_important_keywords: list[str] = Field(default_factory=list)

    def format_for_prompt(self) -> str:
        """Format learned patterns as prompt context."""
        parts = []

        if self.important_domains:
            parts.append(f"Important email domains: {', '.join(self.important_domains)}")
        if self.important_keywords:
            parts.append(f"Important keywords: {', '.join(self.important_keywords)}")
        if self.not_important_domains:
            parts.append(f"Not important email domains: {', '.join(self.not_important_domains)}")
        if self.not_important_keywords:
            parts.append(f"Not important keywords: {', '.join(self.not_important_keywords)}")

        if not parts:
            return ""

        return "\n\nLearned Patterns (from previous labeling):\n" + "\n".join(
            f"- {part}" for part in parts
        )


class PatternExtractionRequest(BaseModel):
    """Request to extract patterns from a labeled email."""

    email_id: UUID
    label: Literal["Important", "Not Important"]
    sender_email: str
    email_subject: str
    email_snippet: Optional[str] = None
