"""Gmail label routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user, get_label_service
from ..schemas import ApplyLabelRequest, ApplyLabelResponse
from ..services.label_service import LabelService

router = APIRouter()


@router.post(
    "",
    response_model=ApplyLabelResponse,
    status_code=status.HTTP_200_OK,
)
async def apply_label(
    payload: ApplyLabelRequest,
    user_id: UUID = Depends(get_current_user),
    label_service: LabelService = Depends(get_label_service),
) -> ApplyLabelResponse:
    """Apply a Gmail label to the provided message."""
    # Override user_id from JWT — ignore any user_id in the request body
    payload.user_id = user_id
    try:
        return await label_service.apply_label(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
