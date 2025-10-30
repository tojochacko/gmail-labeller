"""Agent runtime routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_agent_service
from ..schemas import AgentRunRequest, AgentRunResponse, AgentRunStatusResponse
from ..services.agent_service import AgentService

router = APIRouter()


@router.post(
    "",
    response_model=AgentRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_agent_run(
    payload: AgentRunRequest,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentRunResponse:
    """Start an agent run for a Gmail email."""
    return await agent_service.trigger_agent_run(payload)


@router.get(
    "/{run_id}",
    response_model=AgentRunStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def get_agent_run(
    run_id: UUID,
    agent_service: AgentService = Depends(get_agent_service),
) -> AgentRunStatusResponse:
    """Retrieve the status for an agent run."""
    result = await agent_service.get_agent_run(run_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return result
