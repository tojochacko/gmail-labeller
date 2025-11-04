# AI Learning Feature - Implementation Plan

## Overview

Implement a feedback loop system that enables the AI agent to learn from previous email labeling decisions. The system will extract and store domains and keywords from labeled emails, then use this historical data to improve future labeling accuracy. Users will have full control to manually edit these learned patterns.

## Design Principles

- **KISS**: Keep the learning mechanism simple - just domains and keywords
- **YAGNI**: Implement only what's needed now (no complex ML models)
- **User Control**: Users can override and customize learned patterns
- **Privacy**: All learning is user-specific (no cross-user data sharing)

## Architecture Components

### 1. Database Schema

Create a new table `label_patterns` to store learned patterns per user:

```sql
-- ============================================
-- Label Patterns Table (AI Learning)
-- ============================================
CREATE TABLE IF NOT EXISTS label_patterns (
  pattern_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  label_type VARCHAR(50) NOT NULL,
  pattern_type VARCHAR(50) NOT NULL,
  pattern_value TEXT NOT NULL,
  confidence_score DECIMAL(3,2) DEFAULT 1.0,
  occurrence_count INTEGER DEFAULT 1,
  last_seen_at TIMESTAMPTZ DEFAULT NOW(),
  is_user_defined BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),

  CONSTRAINT valid_label_type CHECK (label_type IN ('Important', 'Not Important')),
  CONSTRAINT valid_pattern_type CHECK (pattern_type IN ('domain', 'keyword')),
  CONSTRAINT valid_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
  CONSTRAINT unique_user_pattern UNIQUE(user_id, label_type, pattern_type, pattern_value)
);

COMMENT ON TABLE label_patterns IS 'Learned patterns from email labeling for AI improvement';
COMMENT ON COLUMN label_patterns.label_type IS 'Label category: Important or Not Important';
COMMENT ON COLUMN label_patterns.pattern_type IS 'Type of pattern: domain or keyword';
COMMENT ON COLUMN label_patterns.pattern_value IS 'The actual domain or keyword value';
COMMENT ON COLUMN label_patterns.confidence_score IS 'Confidence score 0.0-1.0, increases with occurrences';
COMMENT ON COLUMN label_patterns.occurrence_count IS 'Number of times this pattern appeared';
COMMENT ON COLUMN label_patterns.is_user_defined IS 'True if manually added/edited by user';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_label_patterns_user_id ON label_patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_label_patterns_label_type ON label_patterns(label_type);
CREATE INDEX IF NOT EXISTS idx_label_patterns_pattern_type ON label_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_label_patterns_confidence ON label_patterns(confidence_score DESC);

-- RLS Policy
ALTER TABLE label_patterns ENABLE ROW LEVEL SECURITY;

CREATE POLICY label_patterns_policy ON label_patterns
  FOR ALL
  USING (user_id = auth.uid());

-- Updated_at trigger
CREATE TRIGGER update_label_patterns_updated_at
  BEFORE UPDATE ON label_patterns
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();
```

**Additional Email Metadata:**

Update the `emails` table to track applied labels:

```sql
-- Add columns to track applied labels
ALTER TABLE emails ADD COLUMN IF NOT EXISTS applied_label VARCHAR(50);
ALTER TABLE emails ADD COLUMN IF NOT EXISTS label_applied_at TIMESTAMPTZ;
ALTER TABLE emails ADD COLUMN IF NOT EXISTS sender_domain VARCHAR(255);

COMMENT ON COLUMN emails.applied_label IS 'Label actually applied by user';
COMMENT ON COLUMN emails.label_applied_at IS 'Timestamp when label was applied';
COMMENT ON COLUMN emails.sender_domain IS 'Extracted sender domain for pattern learning';

-- Index for pattern analysis
CREATE INDEX IF NOT EXISTS idx_emails_applied_label ON emails(applied_label);
CREATE INDEX IF NOT EXISTS idx_emails_sender_domain ON emails(sender_domain);
```

### 2. Backend - Pydantic Schemas

Create new schemas in `backend/app/schemas/label_patterns.py`:

```python
"""Label patterns schemas for AI learning."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LabelPatternBase(BaseModel):
    """Base schema for label patterns."""

    label_type: Literal["Important", "Not Important"] = Field(
        ..., description="Category this pattern belongs to"
    )
    pattern_type: Literal["domain", "keyword"] = Field(
        ..., description="Type of pattern"
    )
    pattern_value: str = Field(
        ..., min_length=1, max_length=500, description="The pattern value"
    )
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
    """Complete label pattern with database fields."""

    pattern_id: UUID
    user_id: UUID
    occurrence_count: int = Field(default=1)
    last_seen_at: datetime
    is_user_defined: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
            parts.append(
                f"Important email domains: {', '.join(self.important_domains)}"
            )
        if self.important_keywords:
            parts.append(
                f"Important keywords: {', '.join(self.important_keywords)}"
            )
        if self.not_important_domains:
            parts.append(
                f"Not important email domains: {', '.join(self.not_important_domains)}"
            )
        if self.not_important_keywords:
            parts.append(
                f"Not important keywords: {', '.join(self.not_important_keywords)}"
            )

        if not parts:
            return ""

        return (
            "\n\nLearned Patterns (from previous labeling):\n"
            + "\n".join(f"- {part}" for part in parts)
        )


class PatternExtractionRequest(BaseModel):
    """Request to extract patterns from a labeled email."""

    email_id: UUID
    applied_label: Literal["Important", "Not Important"]
    sender_email: str
    email_subject: str
    email_snippet: Optional[str] = None
```

### 3. Backend - Pattern Learning Service

Create `backend/app/services/pattern_learning_service.py`:

```python
"""Service for learning patterns from labeled emails."""

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from backend.app.schemas.label_patterns import (
    LabelPattern,
    LearnedContext,
    PatternExtractionRequest,
)
from backend.app.services.supabase_service import SupabaseService

import logging

logger = logging.getLogger(__name__)


class PatternLearningService:
    """Extract and manage learned patterns from labeled emails."""

    # Common stop words to exclude from keyword extraction
    STOP_WORDS = {
        "the", "be", "to", "of", "and", "a", "in", "that", "have",
        "i", "it", "for", "not", "on", "with", "he", "as", "you",
        "do", "at", "this", "but", "his", "by", "from", "they",
        "we", "say", "her", "she", "or", "an", "will", "my", "one",
        "all", "would", "there", "their", "what", "so", "up", "out",
        "if", "about", "who", "get", "which", "go", "me", "when",
        "make", "can", "like", "time", "no", "just", "him", "know",
        "take", "people", "into", "year", "your", "good", "some",
        "could", "them", "see", "other", "than", "then", "now",
        "look", "only", "come", "its", "over", "think", "also",
        "back", "after", "use", "two", "how", "our", "work", "first",
        "well", "way", "even", "new", "want", "because", "any",
        "these", "give", "day", "most", "us", "is", "was", "are",
        "been", "has", "had", "were", "said", "did", "having",
    }

    # Minimum word length for keywords
    MIN_KEYWORD_LENGTH = 4

    # Maximum keywords to extract per email
    MAX_KEYWORDS_PER_EMAIL = 5

    def __init__(self, supabase: SupabaseService):
        """Initialize pattern learning service."""
        self._supabase = supabase

    async def extract_and_store_patterns(
        self, request: PatternExtractionRequest, user_id: UUID
    ) -> dict[str, int]:
        """Extract patterns from labeled email and store them."""
        patterns_added = {"domains": 0, "keywords": 0}

        # Extract domain
        domain = self._extract_domain(request.sender_email)
        if domain:
            await self._upsert_pattern(
                user_id=user_id,
                label_type=request.applied_label,
                pattern_type="domain",
                pattern_value=domain,
            )
            patterns_added["domains"] = 1

        # Extract keywords
        keywords = self._extract_keywords(
            request.email_subject, request.email_snippet
        )
        for keyword in keywords:
            await self._upsert_pattern(
                user_id=user_id,
                label_type=request.applied_label,
                pattern_type="keyword",
                pattern_value=keyword,
            )
        patterns_added["keywords"] = len(keywords)

        logger.info(
            f"Extracted {patterns_added['domains']} domains and "
            f"{patterns_added['keywords']} keywords for user {user_id}"
        )

        return patterns_added

    def _extract_domain(self, email: str) -> Optional[str]:
        """Extract domain from email address."""
        match = re.search(r"@([\w\.-]+)", email)
        if match:
            return match.group(1).lower()
        return None

    def _extract_keywords(
        self, subject: str, snippet: Optional[str] = None
    ) -> list[str]:
        """Extract meaningful keywords from email content."""
        # Combine subject and snippet
        text = subject or ""
        if snippet:
            text += " " + snippet

        # Normalize: lowercase and remove special characters
        text = re.sub(r"[^\w\s]", " ", text.lower())

        # Tokenize and filter
        words = text.split()
        filtered_words = [
            word
            for word in words
            if len(word) >= self.MIN_KEYWORD_LENGTH
            and word not in self.STOP_WORDS
            and not word.isdigit()
        ]

        # Count frequency and take top N
        word_counts = Counter(filtered_words)
        top_keywords = [
            word for word, _ in word_counts.most_common(self.MAX_KEYWORDS_PER_EMAIL)
        ]

        return top_keywords

    async def _upsert_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> None:
        """Insert or update a pattern (increment occurrence)."""
        await self._supabase.upsert_label_pattern(
            user_id=user_id,
            label_type=label_type,
            pattern_type=pattern_type,
            pattern_value=pattern_value,
        )

    async def get_learned_context(self, user_id: UUID) -> LearnedContext:
        """Retrieve all learned patterns for a user, formatted for prompts."""
        patterns = await self._supabase.get_label_patterns(user_id=user_id)

        context = LearnedContext()

        for pattern in patterns:
            if pattern.label_type == "Important":
                if pattern.pattern_type == "domain":
                    context.important_domains.append(pattern.pattern_value)
                elif pattern.pattern_type == "keyword":
                    context.important_keywords.append(pattern.pattern_value)
            elif pattern.label_type == "Not Important":
                if pattern.pattern_type == "domain":
                    context.not_important_domains.append(pattern.pattern_value)
                elif pattern.pattern_type == "keyword":
                    context.not_important_keywords.append(pattern.pattern_value)

        return context

    async def get_patterns_by_label(
        self, user_id: UUID, label_type: str
    ) -> dict[str, list[str]]:
        """Get patterns grouped by type for a specific label."""
        patterns = await self._supabase.get_label_patterns(
            user_id=user_id, label_type=label_type
        )

        result = {"domains": [], "keywords": []}

        for pattern in patterns:
            if pattern.pattern_type == "domain":
                result["domains"].append(pattern.pattern_value)
            elif pattern.pattern_type == "keyword":
                result["keywords"].append(pattern.pattern_value)

        return result
```

### 4. Backend - Supabase Service Extensions

Add methods to `backend/app/services/supabase_service.py`:

```python
# Add these methods to the SupabaseService class

async def upsert_label_pattern(
    self,
    user_id: UUID,
    label_type: str,
    pattern_type: str,
    pattern_value: str,
) -> None:
    """Insert or update a label pattern (increment occurrence)."""
    try:
        # Check if pattern exists
        response = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("label_type", label_type)
            .eq("pattern_type", pattern_type)
            .eq("pattern_value", pattern_value)
            .execute()
        )

        now = datetime.now(timezone.utc)

        if response.data:
            # Pattern exists - increment occurrence count
            existing = response.data[0]
            new_count = existing["occurrence_count"] + 1
            new_confidence = min(1.0, 0.5 + (new_count * 0.1))  # Increase confidence

            self.client.table("label_patterns").update({
                "occurrence_count": new_count,
                "confidence_score": new_confidence,
                "last_seen_at": now.isoformat(),
            }).eq("pattern_id", existing["pattern_id"]).execute()
        else:
            # New pattern - insert
            self.client.table("label_patterns").insert({
                "user_id": str(user_id),
                "label_type": label_type,
                "pattern_type": pattern_type,
                "pattern_value": pattern_value,
                "confidence_score": 0.5,  # Initial confidence
                "occurrence_count": 1,
                "last_seen_at": now.isoformat(),
                "is_user_defined": False,
            }).execute()

    except Exception as e:
        logger.error(f"Error upserting label pattern: {e}")
        raise


async def get_label_patterns(
    self,
    user_id: UUID,
    label_type: Optional[str] = None,
    pattern_type: Optional[str] = None,
    min_confidence: float = 0.3,
) -> list[dict]:
    """Retrieve label patterns for a user with optional filters."""
    try:
        query = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", str(user_id))
            .gte("confidence_score", min_confidence)
            .order("confidence_score", desc=True)
        )

        if label_type:
            query = query.eq("label_type", label_type)
        if pattern_type:
            query = query.eq("pattern_type", pattern_type)

        response = query.execute()
        return response.data or []

    except Exception as e:
        logger.error(f"Error retrieving label patterns: {e}")
        raise


async def create_user_defined_pattern(
    self,
    user_id: UUID,
    label_type: str,
    pattern_type: str,
    pattern_value: str,
) -> UUID:
    """Create a user-defined pattern."""
    try:
        response = self.client.table("label_patterns").insert({
            "user_id": str(user_id),
            "label_type": label_type,
            "pattern_type": pattern_type,
            "pattern_value": pattern_value.strip().lower(),
            "confidence_score": 1.0,  # User-defined = high confidence
            "occurrence_count": 1,
            "is_user_defined": True,
        }).execute()

        return UUID(response.data[0]["pattern_id"])

    except Exception as e:
        logger.error(f"Error creating user-defined pattern: {e}")
        raise


async def update_label_pattern(
    self, pattern_id: UUID, updates: dict
) -> None:
    """Update a label pattern."""
    try:
        self.client.table("label_patterns").update(updates).eq(
            "pattern_id", str(pattern_id)
        ).execute()
    except Exception as e:
        logger.error(f"Error updating label pattern: {e}")
        raise


async def delete_label_pattern(self, pattern_id: UUID) -> None:
    """Delete a label pattern."""
    try:
        self.client.table("label_patterns").delete().eq(
            "pattern_id", str(pattern_id)
        ).execute()
    except Exception as e:
        logger.error(f"Error deleting label pattern: {e}")
        raise


async def update_email_label(
    self,
    email_id: UUID,
    applied_label: str,
    sender_domain: Optional[str] = None,
) -> None:
    """Update email with applied label and metadata."""
    try:
        updates = {
            "applied_label": applied_label,
            "label_applied_at": datetime.now(timezone.utc).isoformat(),
        }

        if sender_domain:
            updates["sender_domain"] = sender_domain

        self.client.table("emails").update(updates).eq(
            "id", str(email_id)
        ).execute()

    except Exception as e:
        logger.error(f"Error updating email label: {e}")
        raise
```

### 5. Backend - API Routes

Create `backend/app/routes/patterns.py`:

```python
"""API routes for label pattern management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.schemas.label_patterns import (
    LabelPattern,
    LabelPatternCreate,
    LabelPatternListResponse,
    LabelPatternUpdate,
    LearnedContext,
    PatternExtractionRequest,
)
from backend.app.services.pattern_learning_service import PatternLearningService
from backend.app.services.supabase_service import SupabaseService

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


def get_pattern_service() -> PatternLearningService:
    """Dependency: Get pattern learning service."""
    supabase = SupabaseService()
    return PatternLearningService(supabase=supabase)


@router.post(
    "/extract",
    status_code=status.HTTP_201_CREATED,
    summary="Extract patterns from labeled email",
)
async def extract_patterns(
    request: PatternExtractionRequest,
    user_id: UUID = Query(..., description="User ID"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> dict:
    """
    Extract and store patterns from a labeled email.

    This endpoint should be called after a user applies a label to an email.
    It will extract domains and keywords to improve future AI suggestions.
    """
    patterns_added = await service.extract_and_store_patterns(
        request=request, user_id=user_id
    )

    return {
        "message": "Patterns extracted successfully",
        "patterns_added": patterns_added,
    }


@router.get(
    "/",
    response_model=LabelPatternListResponse,
    summary="List all learned patterns",
)
async def list_patterns(
    user_id: UUID = Query(..., description="User ID"),
    label_type: Optional[str] = Query(None, description="Filter by label type"),
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPatternListResponse:
    """
    List all learned patterns for a user.

    Optional filters:
    - label_type: "Important" or "Not Important"
    - pattern_type: "domain" or "keyword"
    """
    supabase = service._supabase
    patterns_data = await supabase.get_label_patterns(
        user_id=user_id,
        label_type=label_type,
        pattern_type=pattern_type,
    )

    patterns = [LabelPattern(**data) for data in patterns_data]

    return LabelPatternListResponse(
        patterns=patterns,
        total=len(patterns),
    )


@router.get(
    "/context",
    response_model=LearnedContext,
    summary="Get learned context for AI prompt",
)
async def get_learned_context(
    user_id: UUID = Query(..., description="User ID"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LearnedContext:
    """
    Retrieve learned patterns formatted for AI prompt injection.

    This endpoint is used by the agent service to enhance prompts
    with historical learning data.
    """
    return await service.get_learned_context(user_id=user_id)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelPattern,
    summary="Create user-defined pattern",
)
async def create_pattern(
    pattern: LabelPatternCreate,
    user_id: UUID = Query(..., description="User ID"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """
    Create a user-defined pattern manually.

    This allows users to add custom domains or keywords
    without waiting for the AI to learn them.
    """
    supabase = service._supabase

    pattern_id = await supabase.create_user_defined_pattern(
        user_id=user_id,
        label_type=pattern.label_type,
        pattern_type=pattern.pattern_type,
        pattern_value=pattern.pattern_value,
    )

    # Fetch the created pattern
    patterns = await supabase.get_label_patterns(user_id=user_id)
    created = next(p for p in patterns if p["pattern_id"] == str(pattern_id))

    return LabelPattern(**created)


@router.patch(
    "/{pattern_id}",
    response_model=LabelPattern,
    summary="Update a pattern",
)
async def update_pattern(
    pattern_id: UUID,
    updates: LabelPatternUpdate,
    user_id: UUID = Query(..., description="User ID"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """
    Update an existing pattern.

    Users can modify confidence scores or pattern values.
    """
    supabase = service._supabase

    # Verify pattern belongs to user
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)

    if not pattern_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found",
        )

    # Update pattern
    update_data = updates.model_dump(exclude_unset=True)
    if update_data:
        await supabase.update_label_pattern(
            pattern_id=pattern_id, updates=update_data
        )

    # Fetch updated pattern
    patterns = await supabase.get_label_patterns(user_id=user_id)
    updated = next(p for p in patterns if p["pattern_id"] == str(pattern_id))

    return LabelPattern(**updated)


@router.delete(
    "/{pattern_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pattern",
)
async def delete_pattern(
    pattern_id: UUID,
    user_id: UUID = Query(..., description="User ID"),
    service: PatternLearningService = Depends(get_pattern_service),
) -> None:
    """
    Delete a learned pattern.

    Users can remove patterns they don't want the AI to consider.
    """
    supabase = service._supabase

    # Verify pattern belongs to user
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)

    if not pattern_exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pattern not found",
        )

    await supabase.delete_label_pattern(pattern_id=pattern_id)
```

Update `backend/app/routes/__init__.py` to include new router:

```python
# Add to existing routers
from backend.app.routes.patterns import router as patterns_router

# In the route registration section
app.include_router(patterns_router)
```

### 6. Backend - Agent Service Integration

Update `backend/app/services/agent_service.py` to inject learned context:

```python
# Add import
from backend.app.services.pattern_learning_service import PatternLearningService

# In AgentService class, add to __init__:
def __init__(self):
    self._settings = get_settings()
    self._supabase = SupabaseService()
    self._mock_runs: dict = {}
    self._pattern_service = PatternLearningService(supabase=self._supabase)

# Modify trigger_agent_run method to include learned context:
async def trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
    """Trigger an agent run with learned context injection."""
    if self._is_mock_mode():
        return await self._mock_trigger_agent_run(request)

    # Fetch learned patterns for this user
    learned_context = await self._pattern_service.get_learned_context(
        user_id=request.user_id
    )

    # Inject learned context into prompt
    enhanced_prompt = request.prompt or ""
    context_text = learned_context.format_for_prompt()

    if context_text:
        enhanced_prompt = f"{enhanced_prompt}\n{context_text}"

    # Continue with agent runtime call (existing logic)
    # Pass enhanced_prompt instead of request.prompt
    ...
```

### 7. Backend - Label Application Workflow

Update `backend/app/routes/labels.py` to trigger pattern extraction:

```python
# Add after label application success
from backend.app.schemas.label_patterns import PatternExtractionRequest
from backend.app.services.pattern_learning_service import PatternLearningService

@router.post("/api/labels/apply")
async def apply_label(
    # existing parameters
):
    # ... existing label application logic ...

    # After successfully applying label, extract patterns
    pattern_service = PatternLearningService(supabase=supabase_service)

    try:
        # Extract sender email from the email record
        email_data = await supabase_service.get_email_by_id(email_id)

        extraction_request = PatternExtractionRequest(
            email_id=email_id,
            applied_label=label_to_apply,
            sender_email=email_data["sender_email"],  # Ensure this field exists
            email_subject=email_data["subject"],
            email_snippet=email_data["snippet"],
        )

        await pattern_service.extract_and_store_patterns(
            request=extraction_request,
            user_id=user_id,
        )

        logger.info(f"Patterns extracted for email {email_id}")
    except Exception as e:
        # Don't fail the label application if pattern extraction fails
        logger.warning(f"Pattern extraction failed: {e}")

    return {"message": "Label applied successfully"}
```

### 8. Frontend - UI Components

Create a new settings/patterns management page:

**File**: `electron-app/src/components/PatternManager.tsx`

```typescript
import React, { useEffect, useState } from 'react';

interface LabelPattern {
  pattern_id: string;
  label_type: 'Important' | 'Not Important';
  pattern_type: 'domain' | 'keyword';
  pattern_value: string;
  confidence_score: number;
  occurrence_count: number;
  is_user_defined: boolean;
}

interface PatternManagerProps {
  userId: string;
}

export const PatternManager: React.FC<PatternManagerProps> = ({ userId }) => {
  const [patterns, setPatterns] = useState<LabelPattern[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<{
    labelType?: string;
    patternType?: string;
  }>({});
  const [newPattern, setNewPattern] = useState({
    label_type: 'Important' as const,
    pattern_type: 'domain' as const,
    pattern_value: '',
  });

  useEffect(() => {
    fetchPatterns();
  }, [userId, filter]);

  const fetchPatterns = async () => {
    try {
      setLoading(true);
      const queryParams = new URLSearchParams({
        user_id: userId,
        ...(filter.labelType && { label_type: filter.labelType }),
        ...(filter.patternType && { pattern_type: filter.patternType }),
      });

      const response = await fetch(
        `http://localhost:8000/api/patterns?${queryParams}`
      );
      const data = await response.json();
      setPatterns(data.patterns);
    } catch (error) {
      console.error('Failed to fetch patterns:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreatePattern = async () => {
    if (!newPattern.pattern_value.trim()) {
      alert('Please enter a pattern value');
      return;
    }

    try {
      const response = await fetch(
        `http://localhost:8000/api/patterns?user_id=${userId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(newPattern),
        }
      );

      if (response.ok) {
        setNewPattern({
          label_type: 'Important',
          pattern_type: 'domain',
          pattern_value: '',
        });
        fetchPatterns();
      }
    } catch (error) {
      console.error('Failed to create pattern:', error);
    }
  };

  const handleDeletePattern = async (patternId: string) => {
    if (!confirm('Are you sure you want to delete this pattern?')) {
      return;
    }

    try {
      const response = await fetch(
        `http://localhost:8000/api/patterns/${patternId}?user_id=${userId}`,
        { method: 'DELETE' }
      );

      if (response.ok) {
        fetchPatterns();
      }
    } catch (error) {
      console.error('Failed to delete pattern:', error);
    }
  };

  return (
    <div className="pattern-manager">
      <h2>AI Learning Patterns</h2>

      {/* Filters */}
      <div className="filters">
        <select
          value={filter.labelType || ''}
          onChange={(e) =>
            setFilter({ ...filter, labelType: e.target.value || undefined })
          }
        >
          <option value="">All Labels</option>
          <option value="Important">Important</option>
          <option value="Not Important">Not Important</option>
        </select>

        <select
          value={filter.patternType || ''}
          onChange={(e) =>
            setFilter({ ...filter, patternType: e.target.value || undefined })
          }
        >
          <option value="">All Types</option>
          <option value="domain">Domains</option>
          <option value="keyword">Keywords</option>
        </select>
      </div>

      {/* Create New Pattern */}
      <div className="create-pattern">
        <h3>Add Custom Pattern</h3>
        <select
          value={newPattern.label_type}
          onChange={(e) =>
            setNewPattern({
              ...newPattern,
              label_type: e.target.value as 'Important' | 'Not Important',
            })
          }
        >
          <option value="Important">Important</option>
          <option value="Not Important">Not Important</option>
        </select>

        <select
          value={newPattern.pattern_type}
          onChange={(e) =>
            setNewPattern({
              ...newPattern,
              pattern_type: e.target.value as 'domain' | 'keyword',
            })
          }
        >
          <option value="domain">Domain</option>
          <option value="keyword">Keyword</option>
        </select>

        <input
          type="text"
          value={newPattern.pattern_value}
          onChange={(e) =>
            setNewPattern({ ...newPattern, pattern_value: e.target.value })
          }
          placeholder="Enter domain or keyword..."
        />

        <button onClick={handleCreatePattern}>Add Pattern</button>
      </div>

      {/* Patterns List */}
      {loading ? (
        <div>Loading patterns...</div>
      ) : (
        <div className="patterns-list">
          <table>
            <thead>
              <tr>
                <th>Label</th>
                <th>Type</th>
                <th>Value</th>
                <th>Confidence</th>
                <th>Occurrences</th>
                <th>Source</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {patterns.map((pattern) => (
                <tr key={pattern.pattern_id}>
                  <td>
                    <span
                      className={`label-badge ${
                        pattern.label_type === 'Important'
                          ? 'important'
                          : 'not-important'
                      }`}
                    >
                      {pattern.label_type}
                    </span>
                  </td>
                  <td>{pattern.pattern_type}</td>
                  <td>{pattern.pattern_value}</td>
                  <td>{(pattern.confidence_score * 100).toFixed(0)}%</td>
                  <td>{pattern.occurrence_count}</td>
                  <td>
                    {pattern.is_user_defined ? '👤 Manual' : '🤖 Learned'}
                  </td>
                  <td>
                    <button
                      onClick={() => handleDeletePattern(pattern.pattern_id)}
                      className="delete-btn"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
```

**Add to App.tsx**:

```typescript
import { PatternManager } from './components/PatternManager';

// Add a new tab or section for pattern management
<div className="settings-tab">
  <PatternManager userId={currentUserId} />
</div>
```

**Add CSS** (`electron-app/src/components/PatternManager.css`):

```css
.pattern-manager {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.filters {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.filters select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.create-pattern {
  background: #f5f5f5;
  padding: 20px;
  border-radius: 8px;
  margin-bottom: 30px;
}

.create-pattern h3 {
  margin-top: 0;
  margin-bottom: 15px;
}

.create-pattern select,
.create-pattern input {
  padding: 8px 12px;
  margin-right: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
}

.create-pattern input {
  flex: 1;
  min-width: 300px;
}

.create-pattern button {
  padding: 8px 16px;
  background: #007bff;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.create-pattern button:hover {
  background: #0056b3;
}

.patterns-list {
  overflow-x: auto;
}

.patterns-list table {
  width: 100%;
  border-collapse: collapse;
  background: white;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}

.patterns-list th,
.patterns-list td {
  padding: 12px;
  text-align: left;
  border-bottom: 1px solid #eee;
}

.patterns-list th {
  background: #f8f9fa;
  font-weight: 600;
  color: #495057;
}

.label-badge {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}

.label-badge.important {
  background: #e3f2fd;
  color: #1976d2;
}

.label-badge.not-important {
  background: #fce4ec;
  color: #c2185b;
}

.delete-btn {
  padding: 6px 12px;
  background: #dc3545;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.delete-btn:hover {
  background: #c82333;
}
```

## MVP Implementation Plan

The MVP focuses on core functionality: automatic pattern learning and basic user control. Post-MVP improvements add advanced features and analytics.

---

## Phase 1: MVP - Core Learning System

### Phase 1.1: Database & Backend Foundation
**Estimated Time**: 2-3 days
**Goal**: Establish data storage and pattern extraction logic

**Tasks**:
1. **Database Setup**
   - Execute SQL migration for `label_patterns` table in Supabase
   - Add columns to `emails` table: `applied_label`, `label_applied_at`, `sender_domain`
   - Verify indexes and RLS policies are active
   - Test database constraints and triggers

2. **Backend Schemas**
   - Create `backend/app/schemas/label_patterns.py`
   - Define all Pydantic models: `LabelPatternBase`, `LabelPatternCreate`, `LabelPattern`, `LearnedContext`, etc.
   - Add type validation and field constraints

3. **Pattern Learning Service**
   - Create `backend/app/services/pattern_learning_service.py`
   - Implement `_extract_domain()` method
   - Implement `_extract_keywords()` with stop word filtering
   - Implement `extract_and_store_patterns()` method
   - Implement `get_learned_context()` method
   - Add comprehensive logging

4. **Supabase Service Extensions**
   - Add `upsert_label_pattern()` method to `SupabaseService`
   - Add `get_label_patterns()` method with filtering
   - Add `update_email_label()` method
   - Add error handling for all database operations

**Deliverables**:
- ✅ Database schema deployed to Supabase
- ✅ Pattern extraction logic functional
- ✅ Supabase service extended with pattern methods
- ✅ Comprehensive logging in place

**Testing Note**: Backend testing runs in DevContainer via `uv run pytest` - developers will run tests manually as needed.

---

### Phase 1.2: API Routes & Agent Integration
**Estimated Time**: 2-3 days
**Goal**: Expose pattern APIs and integrate with AI agent

**Tasks**:
1. **Pattern API Routes**
   - Create `backend/app/routes/patterns.py`
   - Implement `POST /api/patterns/extract` endpoint
   - Implement `GET /api/patterns` endpoint (list with filters)
   - Implement `GET /api/patterns/context` endpoint
   - Add OpenAPI documentation for all endpoints
   - Register routes in `backend/app/routes/__init__.py`

2. **Label Workflow Integration**
   - Update `backend/app/routes/labels.py`
   - Add pattern extraction trigger after label application
   - Extract sender email from email record
   - Handle extraction failures gracefully (don't block label application)

3. **Agent Service Enhancement**
   - Update `backend/app/services/agent_service.py`
   - Add `_pattern_service` to `AgentService.__init__()`
   - Fetch learned context in `trigger_agent_run()`
   - Inject learned context into agent prompt
   - Update mock mode to simulate learned context usage

4. **Error Handling**
   - Add try-catch blocks for all pattern operations
   - Log warnings for non-critical failures
   - Return appropriate HTTP status codes
   - Add validation error messages

**Deliverables**:
- ✅ RESTful API for pattern extraction and retrieval
- ✅ Label application triggers pattern learning
- ✅ Agent prompts enhanced with learned context
- ✅ Comprehensive error handling
- ✅ API documentation in Swagger/OpenAPI

**Testing**: API endpoints can be tested with `curl` or Postman during development.

---

### Phase 1.3: Frontend Pattern Viewer (Read-Only MVP)
**Estimated Time**: 2-3 days
**Goal**: Display learned patterns to users

**Tasks**:
1. **Pattern Viewer Component**
   - Create `electron-app/src/components/PatternViewer.tsx`
   - Display patterns in a table (label type, pattern type, value, confidence, occurrences)
   - Add filter dropdowns (label type, pattern type)
   - Implement pagination (50 patterns per page)
   - Add loading states and error handling

2. **UI Integration**
   - Add "View Learned Patterns" tab/section to `App.tsx`
   - Fetch patterns from backend on component mount
   - Display empty state when no patterns exist
   - Add refresh button

3. **Styling**
   - Create `electron-app/src/components/PatternViewer.css`
   - Style table with proper spacing and borders
   - Add color-coded badges for label types
   - Add icons for pattern types (🌐 domain, 🔑 keyword)
   - Ensure responsive design

4. **Frontend Testing**
   - Run TypeScript compilation: `npx tsc --noEmit`
   - Run linting: `pnpm lint`
   - Fix any linting errors: `pnpm lint --fix`
   - Test UI manually on host machine (not DevContainer)

**Deliverables**:
- ✅ Users can view all learned patterns
- ✅ Patterns are filterable and paginated
- ✅ UI is clean and responsive
- ✅ TypeScript compilation passes
- ✅ Linting passes without errors

---

### Phase 1.4: MVP Testing & Documentation
**Estimated Time**: 1-2 days
**Goal**: Validate end-to-end workflow and document usage

**Tasks**:
1. **End-to-End Testing Scenario**
   - Label 5 emails as "Important" from same domain
   - Label 5 emails as "Not Important" from different domain
   - Verify patterns extracted correctly in database
   - Verify patterns appear in UI
   - Trigger new agent run and verify learned context in logs
   - Test filter functionality in UI

2. **Frontend Testing**
   - Run full TypeScript build: `cd electron-app && pnpm build`
   - Run linting: `pnpm lint`
   - Test all UI interactions manually

3. **Documentation**
   - Update `README.md` with feature description
   - Document API endpoints in `API_DOCUMENTATION.md`
   - Create user guide: `docs/PATTERN_LEARNING_GUIDE.md`
   - Update database schema documentation

4. **Bug Fixes & Polish**
   - Fix any issues discovered during testing
   - Optimize slow database queries
   - Improve error messages
   - Add tooltips to UI elements

**Deliverables**:
- ✅ End-to-end workflow validated
- ✅ Frontend linting and build passing
- ✅ Documentation complete
- ✅ Known bugs fixed

**MVP Success Criteria**:
- ✅ Patterns automatically extracted when emails are labeled
- ✅ Patterns visible in UI with correct data
- ✅ Agent prompts include learned context
- ✅ No crashes or critical errors
- ✅ TypeScript and linting pass for frontend

**Total MVP Time**: 7-11 days

---

## Phase 2: Post-MVP - User Control & Management

### Phase 2.1: Pattern CRUD Operations
**Estimated Time**: 2-3 days
**Goal**: Enable users to manage patterns manually

**Tasks**:
1. **Backend CRUD APIs**
   - Implement `POST /api/patterns` (create user-defined pattern)
   - Implement `PATCH /api/patterns/{id}` (update pattern)
   - Implement `DELETE /api/patterns/{id}` (delete pattern)
   - Add `create_user_defined_pattern()` to `SupabaseService`
   - Add `update_label_pattern()` to `SupabaseService`
   - Add `delete_label_pattern()` to `SupabaseService`

2. **Frontend Pattern Manager**
   - Update `PatternViewer.tsx` to `PatternManager.tsx`
   - Add "Create New Pattern" form
   - Add inline edit buttons for each pattern row
   - Add delete button with confirmation dialog
   - Add success/error toast notifications

3. **Form Validation**
   - Validate pattern value (min 1 char, max 500 chars)
   - Prevent duplicate patterns
   - Sanitize input for XSS prevention
   - Show validation errors inline

4. **Frontend Testing**
   - TypeScript compilation: `npx tsc --noEmit`
   - Linting: `pnpm lint --fix`
   - Manual testing of all CRUD operations

**Deliverables**:
- ✅ Users can create custom patterns
- ✅ Users can edit pattern values and confidence scores
- ✅ Users can delete unwanted patterns
- ✅ All operations validated and secured

---

### Phase 2.2: Performance Optimization
**Estimated Time**: 1-2 days
**Goal**: Ensure scalability for high pattern counts

**Tasks**:
1. **Database Optimization**
   - Implement query result caching (5-minute TTL)
   - Add database query performance logging
   - Test with 1000+ patterns per user
   - Optimize indexes if needed

2. **API Rate Limiting**
   - Add rate limiting to pattern CRUD endpoints
   - Limit: 10 creates/minute, 20 reads/minute
   - Return 429 status with retry-after header

3. **Frontend Optimization**
   - Implement virtual scrolling for large pattern lists
   - Add debouncing to filter inputs
   - Lazy load patterns (load on scroll)
   - Add loading skeletons

4. **Monitoring**
   - Add performance metrics logging
   - Track pattern extraction time
   - Track API endpoint latency
   - Monitor database query performance

**Deliverables**:
- ✅ System performs well with 1000+ patterns
- ✅ API rate limiting prevents abuse
- ✅ Frontend remains responsive with large datasets
- ✅ Performance metrics available for analysis

---

### Phase 2.3: User Experience Enhancements
**Estimated Time**: 2-3 days
**Goal**: Polish UX and add convenience features

**Tasks**:
1. **Pattern Analytics Dashboard**
   - Show total patterns count by type
   - Show top 10 most confident patterns
   - Show pattern distribution chart (domains vs keywords)
   - Show learning trend over time

2. **Bulk Operations**
   - Add "Select All" checkbox
   - Add "Delete Selected" button
   - Add "Export Patterns" (CSV download)
   - Add "Import Patterns" (CSV upload)

3. **Smart Suggestions**
   - Show AI-suggested patterns based on email history
   - Allow one-click acceptance of suggestions
   - Show why pattern was suggested

4. **Improved Feedback**
   - Add "Pattern Applied" notification after labeling
   - Show pattern extraction status in real-time
   - Add undo/redo for pattern operations
   - Add keyboard shortcuts

5. **Frontend Testing**
   - TypeScript compilation and linting
   - Manual testing of all new features
   - Cross-browser testing (if applicable)

**Deliverables**:
- ✅ Analytics dashboard provides insights
- ✅ Bulk operations save time
- ✅ Users receive clear feedback
- ✅ UX feels polished and professional

---

## Phase 3: Future Enhancements (Backlog)

### Advanced Features (Not Prioritized)

**Pattern Intelligence**:
- Smart confidence decay for old patterns
- Pattern merging (combine similar keywords)
- Negative learning (learn from AI mistakes)
- Regex pattern support for power users

**Sender Analysis**:
- Track sender behavior consistency
- Temporal patterns (time-based importance)
- Thread context consideration
- Sender reputation scoring

**Collaboration**:
- Optional anonymous pattern sharing
- Team pattern libraries
- Pattern recommendations from community
- A/B testing different pattern strategies

**Multi-Label Support**:
- Beyond binary Important/Not Important
- Support for custom label categories
- Hierarchical labels (Important > Urgent)
- Label priority management

**Natural Language Rules**:
- "Emails from @company.com about 'deadline' are important"
- Rule builder UI with drag-and-drop
- Conditional logic (IF-THEN rules)
- Rule conflict detection

**These features should be evaluated based on user feedback and usage metrics before implementation.**

## Testing Strategy

### Backend Testing (DevContainer)

**Note**: Backend Python tests are run manually in the DevContainer by developers as needed. The backend codebase uses `uv run pytest` for testing.

**Example Backend Tests** (for reference, not part of this implementation plan):

```bash
# Developers can run these commands in DevContainer as needed:
cd /workspaces/autogen-test
uv run pytest backend/tests/test_pattern_learning_service.py -v
uv run pytest backend/tests/test_pattern_api.py -v
uv run pytest backend/tests/ --cov=backend/app
```

Backend test coverage includes:
- Pattern extraction logic (`_extract_domain`, `_extract_keywords`)
- Supabase service methods (`upsert_label_pattern`, `get_label_patterns`)
- API endpoint responses and error handling
- Agent service integration with learned context

**Backend testing is the responsibility of developers using the DevContainer environment.**

---

### Frontend Testing (Required for Implementation Plan)

Frontend testing must pass before each phase is considered complete.

**TypeScript Compilation**:
```bash
cd /workspaces/autogen-test/electron-app
npx tsc --noEmit
```

**Linting**:
```bash
cd /workspaces/autogen-test/electron-app
pnpm lint

# Fix auto-fixable issues
pnpm lint --fix
```

**Production Build**:
```bash
cd /workspaces/autogen-test/electron-app
pnpm build
```

**Manual Testing Checklist**:
- [ ] Pattern viewer displays patterns correctly
- [ ] Filters work (label type, pattern type)
- [ ] Pagination works smoothly
- [ ] Loading states display appropriately
- [ ] Error messages are clear and helpful
- [ ] Create pattern form validates inputs
- [ ] Edit pattern saves changes correctly
- [ ] Delete pattern removes pattern from list
- [ ] UI is responsive on different window sizes
- [ ] No console errors in DevTools

---

### End-to-End Test Scenario

**Test Flow** (Manual Testing):

1. **Setup Phase**:
   - Start backend in DevContainer: `uv run uvicorn backend.app.main:create_app --reload --host 0.0.0.0 --port 8000`
   - Start Electron app on host machine: `cd electron-app && pnpm dev`
   - Complete OAuth flow and connect Gmail account

2. **Pattern Learning Test**:
   - Label 3 emails from "boss@bigcorp.com" as "Important"
   - Label 2 emails from "newsletter@marketing.com" as "Not Important"
   - Open Supabase dashboard and verify patterns in `label_patterns` table
   - Expected patterns:
     - Domain: "bigcorp.com" (Important, occurrence_count=3)
     - Domain: "marketing.com" (Not Important, occurrence_count=2)
     - Keywords extracted from subjects

3. **Pattern Viewer Test**:
   - Navigate to "Learned Patterns" tab in Electron app
   - Verify all patterns appear in table
   - Test filters: select "Important" → should show only Important patterns
   - Test filters: select "domain" → should show only domain patterns
   - Verify confidence scores and occurrence counts are correct

4. **Agent Integration Test**:
   - Fetch new email from "boss@bigcorp.com"
   - Trigger agent run
   - Check backend logs: verify learned context appears in prompt
   - Verify AI suggestion considers learned patterns

5. **CRUD Operations Test** (Post-MVP Phase 2.1):
   - Click "Add Pattern" button
   - Create custom pattern: Important, keyword, "urgent"
   - Verify new pattern appears with user-defined badge
   - Edit a pattern's confidence score
   - Delete a pattern, confirm it's removed

6. **Performance Test** (Post-MVP Phase 2.2):
   - Create 100+ patterns (use script if needed)
   - Verify UI remains responsive
   - Test pagination and filtering with large dataset
   - Measure API response times (should be < 200ms)

## Performance Considerations

### Database Optimization

- Use indexes on `user_id`, `label_type`, `pattern_type`, `confidence_score`
- Consider materialized view for frequently accessed patterns
- Implement pagination for pattern lists (limit 100 per page)
- Cache learned context per user (TTL 5 minutes)

### Keyword Extraction Optimization

- Limit to top 5 keywords per email
- Use efficient tokenization (regex split)
- Pre-compiled regex patterns
- Async processing (don't block label application)

### API Rate Limiting

```python
# Add to FastAPI middleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/api/patterns")
@limiter.limit("10/minute")  # Prevent abuse
async def create_pattern(...):
    ...
```

## Security Considerations

1. **Row Level Security**: Enforce user isolation in database
2. **Input Validation**: Sanitize pattern values (XSS prevention)
3. **Rate Limiting**: Prevent pattern spam attacks
4. **Audit Logging**: Track pattern modifications
5. **GDPR Compliance**: Allow pattern export/deletion

## Monitoring & Observability

### Key Metrics

- Pattern extraction success rate
- Average patterns per user
- Agent prompt enhancement effectiveness
- Pattern CRUD operation latency
- User-defined vs auto-learned pattern ratio

### Logging

```python
logger.info(
    "Pattern extracted",
    extra={
        "user_id": str(user_id),
        "label_type": label_type,
        "pattern_type": pattern_type,
        "pattern_value": pattern_value,
        "is_new": is_new_pattern,
    },
)
```

## Future Enhancements

### Phase 2 Features (Post-MVP)

1. **Smart Confidence Decay**: Reduce confidence for old patterns
2. **Pattern Merging**: Combine similar keywords (e.g., "urgent" + "urgently")
3. **Negative Learning**: Learn from user corrections (AI suggested wrong label)
4. **Pattern Analytics**: Show accuracy improvement over time
5. **Export/Import**: Share patterns across devices
6. **Pattern Suggestions**: AI suggests patterns user might want to add
7. **Regex Patterns**: Support regex for advanced users
8. **Bulk Operations**: Bulk add/delete/edit patterns

### Advanced Features (Future Iterations)

1. **Sender Behavior Analysis**: Track sender consistency
2. **Temporal Patterns**: Time-based importance (morning emails from boss)
3. **Thread Context**: Consider email thread history
4. **Collaborative Learning**: (Optional) Share anonymized patterns
5. **Multi-label Support**: Beyond binary Important/Not Important
6. **Natural Language Rules**: "Emails from @company.com about 'deadline' are important"

## Success Criteria

### MVP (Phase 1) Success Metrics

**Functional Requirements**:
- ✅ Patterns automatically extracted when emails are labeled (domain + keywords)
- ✅ Patterns stored in database with proper user isolation (RLS)
- ✅ Patterns visible in UI with filtering and pagination
- ✅ Agent prompts include learned context in subsequent runs
- ✅ Zero data leakage between users
- ✅ No crashes or critical errors

**Performance Requirements**:
- ✅ Pattern extraction completes within 2 seconds
- ✅ API response time < 200ms (p95)
- ✅ UI loads patterns in < 1 second
- ✅ Database queries optimized with proper indexes

**Quality Requirements**:
- ✅ TypeScript compilation passes with no errors
- ✅ Frontend linting passes with no errors
- ✅ All API endpoints documented in Swagger/OpenAPI
- ✅ User documentation complete

### Post-MVP (Phase 2) Success Metrics

**Pattern Management**:
- ✅ Users can create custom patterns without errors
- ✅ Users can edit and delete patterns successfully
- ✅ Pattern CRUD operations have proper validation
- ✅ UI provides clear feedback for all operations

**Performance at Scale**:
- ✅ System handles 1000+ patterns per user smoothly
- ✅ Frontend remains responsive with large datasets
- ✅ API rate limiting prevents abuse

**User Experience**:
- ✅ Analytics dashboard provides actionable insights
- ✅ Bulk operations save user time
- ✅ Pattern management feels polished and professional

### User Experience Goals

**MVP Outcome**:
- Users see improved labeling accuracy after 10-15 labeled emails
- Pattern viewer is intuitive (no training needed)
- System feels responsive (no blocking operations)
- Users understand what the AI learned from their actions

**Post-MVP Outcome**:
- Users trust the AI more over time
- Users actively manage patterns to improve accuracy
- Pattern management becomes part of regular workflow
- Users feel in control of AI learning process

## Documentation Updates Required

1. **API Documentation**: Add pattern endpoints to Swagger/OpenAPI
2. **User Guide**: How to manage learned patterns
3. **Developer Guide**: Pattern extraction algorithm explanation
4. **Database Schema Docs**: Update ER diagram with new table
5. **CHANGELOG.md**: Document new feature addition

## Risk Mitigation

### Technical Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Poor keyword extraction quality | High | Use proven NLP stop words, allow user override |
| Database performance degradation | Medium | Implement indexes, caching, pagination |
| Pattern explosion (too many patterns) | Medium | Set max patterns per user (e.g., 1000), auto-prune low confidence |
| Prompt becomes too long | Medium | Limit top N patterns by confidence, summarize |

### UX Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users don't understand feature | High | Clear onboarding, tooltips, examples |
| Feature feels overwhelming | Medium | Start with simple view, progressive disclosure |
| Users lose trust in AI | High | Show transparency (why AI suggested label), allow easy override |

## Rollout Plan

### Staged Rollout

1. **Internal Testing** (Week 1): Dev team testing
2. **Alpha Testing** (Week 2): 5-10 internal users
3. **Beta Testing** (Week 3-4): 50-100 early adopters
4. **General Availability** (Week 5): All users
5. **Post-Launch Monitoring** (Week 6+): Collect feedback, iterate

### Feature Flags

```python
# config.py
class Settings(BaseSettings):
    ENABLE_PATTERN_LEARNING: bool = Field(default=False)
    PATTERN_LEARNING_MIN_CONFIDENCE: float = Field(default=0.3)
    PATTERN_LEARNING_MAX_PATTERNS_PER_USER: int = Field(default=1000)
```

## Conclusion

This implementation plan provides a comprehensive roadmap for building an AI learning feature that improves email labeling accuracy over time. The design follows KISS and YAGNI principles, focuses on user control, and maintains strict privacy boundaries.

### Implementation Summary

**Phase 1: MVP - Core Learning System**
- **Time**: 7-11 days
- **Goal**: Automatic pattern extraction and basic viewing
- **Deliverables**: Database, backend services, API routes, read-only UI
- **Success**: Patterns automatically learned and displayed to users

**Phase 2: Post-MVP - User Control & Management**
- **Time**: 5-8 days
- **Goal**: Full pattern management, performance optimization, UX polish
- **Deliverables**: CRUD operations, analytics, bulk actions, optimizations
- **Success**: Users actively manage patterns to improve AI accuracy

**Phase 3: Future Enhancements**
- **Timeline**: TBD (based on user feedback)
- **Features**: Advanced intelligence, collaboration, multi-label support
- **Decision**: Evaluate after MVP/Post-MVP usage metrics

### Total Development Time

- **MVP Only**: 7-11 days
- **MVP + Post-MVP**: 12-19 days
- **Team Size**: 1-2 developers
- **Complexity**: Medium

### Design Principles Applied

The feature is designed to be:
- ✅ **Simple to understand**: Domains and keywords are intuitive concepts
- ✅ **Easy to use**: Automatic learning with manual override
- ✅ **Privacy-focused**: All data is user-specific (RLS enforced)
- ✅ **Scalable**: Efficient database design with indexes and caching
- ✅ **Maintainable**: Clear separation of concerns (schemas, services, routes)
- ✅ **User-controlled**: Users can view, create, edit, and delete patterns

### Testing Approach

**Backend**: Developers test manually in DevContainer using `uv run pytest`

**Frontend**: Required testing integrated into implementation phases:
- TypeScript compilation must pass
- Linting must pass (auto-fix applied)
- Manual testing checklist for each phase
- Production build verification

### Recommended Implementation Order

1. **Start with Phase 1.1** (Database & Backend Foundation)
   - Focus on getting pattern extraction working
   - Verify database schema and RLS policies

2. **Continue with Phase 1.2** (API Routes & Agent Integration)
   - Test APIs with curl/Postman
   - Verify learned context in agent logs

3. **Complete Phase 1.3** (Frontend Pattern Viewer)
   - Build read-only UI first
   - Run frontend linting and compilation

4. **Finish Phase 1.4** (MVP Testing & Documentation)
   - Run end-to-end test scenario
   - Document everything for users

5. **Evaluate before Phase 2**
   - Gather user feedback on MVP
   - Decide which Post-MVP features to prioritize
   - Adjust timeline based on learnings

### Next Steps

1. **Review this plan** with stakeholders
2. **Confirm Supabase access** and database migration permissions
3. **Set up development environment** (DevContainer for backend, host machine for Electron)
4. **Begin Phase 1.1** implementation
5. **Schedule checkpoints** at end of each phase for review

---

**Ready to begin implementation!** 🚀
