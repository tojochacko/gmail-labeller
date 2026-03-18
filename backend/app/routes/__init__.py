"""Route registration for the FastAPI app."""

from fastapi import APIRouter

from . import agent, debug, emails, labels, oauth, patterns, review, sessions

api_router = APIRouter(prefix="/api")

api_router.include_router(oauth.router, prefix="/oauth", tags=["oauth"])
api_router.include_router(emails.router, prefix="/emails", tags=["emails"])
api_router.include_router(labels.router, prefix="/labels", tags=["labels"])
api_router.include_router(agent.router, prefix="/runs", tags=["agent-runs"])
api_router.include_router(debug.router, prefix="/debug", tags=["debug"])
api_router.include_router(patterns.router, prefix="/patterns", tags=["patterns"])
api_router.include_router(sessions.router, prefix="/sessions", tags=["sessions"])
api_router.include_router(review.router, prefix="/review", tags=["review"])

__all__ = ["api_router"]
