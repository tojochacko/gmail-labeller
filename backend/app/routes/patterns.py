"""API routes for label pattern management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..dependencies import get_pattern_service
from ..schemas.label_patterns import (
    LabelPattern,
    LabelPatternCreate,
    LabelPatternListResponse,
    LabelPatternUpdate,
    LearnedContext,
    PatternExtractionRequest,
)
from ..services.pattern_learning_service import PatternLearningService

router = APIRouter()


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
    patterns_added = await service.extract_and_store_patterns(request=request, user_id=user_id)

    return {
        "message": "Patterns extracted successfully",
        "patterns_added": patterns_added,
    }


@router.get(
    "",
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
    "",
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
        await supabase.update_label_pattern(pattern_id=pattern_id, updates=update_data)

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
