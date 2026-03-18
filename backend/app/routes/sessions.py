"""Classification session API endpoints."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..dependencies import (
    get_batch_classifier,
    get_classification_session_service,
)
from ..services.batch_classifier import BatchClassifier
from ..services.classification_session_service import ClassificationSessionService

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateSessionRequest(BaseModel):
    """Request payload for creating a classification session."""

    user_id: UUID
    max_results: int = Field(default=10, ge=1, le=50)


class CreateSessionResponse(BaseModel):
    """Response after creating a session."""

    session_id: UUID
    email_count: int
    status: str


class SessionStatusResponse(BaseModel):
    """Session status response."""

    session_id: UUID
    status: str
    email_count: int
    created_at: str
    completed_at: str | None = None


class CleanupResponse(BaseModel):
    """Response after cleaning up a session."""

    session_id: UUID
    emails_deleted: int
    runs_deleted: int
    status: str


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> CreateSessionResponse:
    """Create a new classification session and fetch unlabeled emails into it."""
    try:
        session_id = await session_svc.create_session(
            user_id=request.user_id,
            max_results=request.max_results,
        )
        session = await session_svc.get_session(session_id)
        email_count = session.get("email_count", 0) if session else 0
        return CreateSessionResponse(
            session_id=session_id,
            email_count=email_count,
            status="pending",
        )
    except Exception as e:
        logger.error("Failed to create session: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionStatusResponse)
async def get_session(
    session_id: UUID,
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> SessionStatusResponse:
    """Get the status of a classification session."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionStatusResponse(
        session_id=UUID(session["id"]),
        status=session["status"],
        email_count=session.get("email_count", 0),
        created_at=str(session.get("created_at", "")),
        completed_at=session.get("completed_at"),
    )


@router.post("/{session_id}/run", status_code=status.HTTP_202_ACCEPTED)
async def run_session(
    session_id: UUID,
    background_tasks: BackgroundTasks,
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
    batch_classifier: BatchClassifier = Depends(get_batch_classifier),
) -> dict:
    """Trigger batch LLM classification for all emails in a session (runs in background)."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["status"] not in ("pending", "awaiting_review"):
        raise HTTPException(
            status_code=409,
            detail=f"Session is in status '{session['status']}', cannot run again.",
        )

    user_id = UUID(session["user_id"])

    async def _run_bg() -> None:
        try:
            await batch_classifier.run_batch(session_id=session_id, user_id=user_id)
        except Exception as e:
            logger.error("Background batch classification failed for session %s: %s", session_id, e)

    background_tasks.add_task(_run_bg)
    return {"session_id": str(session_id), "status": "classifying", "message": "Batch started"}


@router.get("/{session_id}/emails")
async def get_session_emails(
    session_id: UUID,
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> dict:
    """Get all emails in a session for review."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    emails = await session_svc.get_session_emails(session_id)
    return {
        "session_id": str(session_id),
        "emails": [e.model_dump(mode="json") for e in emails],
    }


@router.post("/{session_id}/cleanup", response_model=CleanupResponse)
async def cleanup_session(
    session_id: UUID,
    session_svc: ClassificationSessionService = Depends(get_classification_session_service),
) -> CleanupResponse:
    """Delete emails and agent_runs for a session, mark it cleaned_up."""
    session = await session_svc.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await session_svc.cleanup_session(session_id)
    return CleanupResponse(
        session_id=session_id,
        emails_deleted=result["emails_deleted"],
        runs_deleted=result["runs_deleted"],
        status="cleaned_up",
    )
