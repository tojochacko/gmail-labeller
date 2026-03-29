"""FastAPI dependency providers."""

from __future__ import annotations

from uuid import UUID

from fastapi import Depends

from .config import Settings, get_settings
from .db.engine import make_engine, make_session_factory
from .services import (
    AgentService,
    BatchClassifier,
    ClassificationSessionService,
    DBService,
    EmailService,
    GmailService,
    GmailToolkitFactory,
    LabelService,
    PatternLearningService,
    SessionRepository,
)

_db_service: DBService | None = None
_gmail_service: GmailService | None = None


def get_db_service(settings: Settings = Depends(get_settings)) -> DBService:
    global _db_service
    if _db_service is None:
        engine = make_engine(settings.database_url)
        factory = make_session_factory(engine)
        _db_service = DBService(
            session_factory=factory,
            fernet_key=settings.fernet_secret_key.get_secret_value(),
        )
    return _db_service


def get_gmail_service(settings: Settings = Depends(get_settings)) -> GmailService:
    global _gmail_service
    if _gmail_service is None:
        toolkit = GmailToolkitFactory(settings).build()
        _gmail_service = GmailService(toolkit, settings)
    return _gmail_service


def get_email_service(
    gmail_service: GmailService = Depends(get_gmail_service),
    db: DBService = Depends(get_db_service),
    settings: Settings = Depends(get_settings),
) -> EmailService:
    return EmailService(gmail_service, db, settings)


def get_label_service(
    gmail_service: GmailService = Depends(get_gmail_service),
    db: DBService = Depends(get_db_service),
) -> LabelService:
    return LabelService(gmail_service, db)


def get_agent_service(
    settings: Settings = Depends(get_settings),
    db: DBService = Depends(get_db_service),
) -> AgentService:
    return AgentService(settings, db)


def get_pattern_service(
    db: DBService = Depends(get_db_service),
) -> PatternLearningService:
    return PatternLearningService(db)


def get_session_repository(
    db: DBService = Depends(get_db_service),
) -> SessionRepository:
    return SessionRepository(db.session_factory)


def get_classification_session_service(
    session_repo: SessionRepository = Depends(get_session_repository),
    email_service: EmailService = Depends(get_email_service),
) -> ClassificationSessionService:
    return ClassificationSessionService(session_repo, email_service)


def get_batch_classifier(
    session_repo: SessionRepository = Depends(get_session_repository),
    db: DBService = Depends(get_db_service),
    agent_service: AgentService = Depends(get_agent_service),
    gmail_service: GmailService = Depends(get_gmail_service),
) -> BatchClassifier:
    return BatchClassifier(session_repo, db, agent_service, gmail_service)


from .auth import require_auth  # noqa: E402


def get_current_user(user_id: UUID = Depends(require_auth)) -> UUID:
    """Return the authenticated user_id. Override in tests via dependency_overrides."""
    return user_id
