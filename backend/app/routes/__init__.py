"""Route registration for the FastAPI app."""

from fastapi import APIRouter

from . import agent, debug, emails, labels, oauth

api_router = APIRouter(prefix="/api")

api_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])
api_router.include_router(labels.router, prefix="/labels", tags=["labels"])
api_router.include_router(agent.router, prefix="/runs", tags=["agent-runs"])
api_router.include_router(debug.router, prefix="/debug", tags=["debug"])

__all__ = ["api_router"]
