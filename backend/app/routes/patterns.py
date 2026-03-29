"""API routes for label pattern management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user, get_pattern_service
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
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> dict:
    """Extract and store patterns from a labeled email."""
    patterns_added = await service.extract_and_store_patterns(request=request, user_id=user_id)
    return {"message": "Patterns extracted successfully", "patterns_added": patterns_added}


@router.get(
    "",
    response_model=LabelPatternListResponse,
    summary="List all learned patterns",
)
async def list_patterns(
    label_type: Optional[str] = None,
    pattern_type: Optional[str] = None,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPatternListResponse:
    """List all learned patterns for the authenticated user."""
    supabase = service._supabase
    patterns_data = await supabase.get_label_patterns(
        user_id=user_id,
        label_type=label_type,
        pattern_type=pattern_type,
    )
    patterns = [LabelPattern(**data) for data in patterns_data]
    return LabelPatternListResponse(patterns=patterns, total=len(patterns))


@router.get(
    "/context",
    response_model=LearnedContext,
    summary="Get learned context for AI prompt",
)
async def get_learned_context(
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LearnedContext:
    """Retrieve learned patterns formatted for AI prompt injection."""
    return await service.get_learned_context(user_id=user_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=LabelPattern,
    summary="Create user-defined pattern",
)
async def create_pattern(
    pattern: LabelPatternCreate,
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """Create a user-defined pattern manually."""
    supabase = service._supabase
    pattern_id = await supabase.create_user_defined_pattern(
        user_id=user_id,
        label_type=pattern.label_type,
        pattern_type=pattern.pattern_type,
        pattern_value=pattern.pattern_value,
    )
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
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> LabelPattern:
    """Update an existing pattern owned by the authenticated user."""
    supabase = service._supabase
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)
    if not pattern_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    update_data = updates.model_dump(exclude_unset=True)
    if update_data:
        await supabase.update_label_pattern(pattern_id=pattern_id, updates=update_data)
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
    user_id: UUID = Depends(get_current_user),
    service: PatternLearningService = Depends(get_pattern_service),
) -> None:
    """Delete a learned pattern owned by the authenticated user."""
    supabase = service._supabase
    patterns = await supabase.get_label_patterns(user_id=user_id)
    pattern_exists = any(p["pattern_id"] == str(pattern_id) for p in patterns)
    if not pattern_exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found")
    await supabase.delete_label_pattern(pattern_id=pattern_id)
