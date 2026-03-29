"""Shared fixtures for backend tests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import sys

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.append(str(ROOT))

from cryptography.fernet import Fernet  # noqa: E402

from backend.app.auth import create_access_token  # noqa: E402
from backend.app.config import Settings  # noqa: E402
from backend.app.main import create_app  # noqa: E402
from backend.app.dependencies import (  # noqa: E402
    get_agent_service,
    get_current_user,
    get_db_service,
    get_email_service,
    get_gmail_service,
    get_label_service,
)
from backend.app.schemas import (  # noqa: E402
    AgentRunRequest,
    AgentRunResponse,
    AgentRunStatusResponse,
    ApplyLabelRequest,
    ApplyLabelResponse,
    EmailItem,
    GmailTokens,
)
from pydantic import SecretStr  # noqa: E402


class FakeDBService:
    def __init__(self) -> None:
        self.users: dict[UUID, str] = {}
        self.tokens: dict[UUID, GmailTokens] = {}
        self.emails: dict[UUID, EmailItem] = {}
        self.agent_runs: dict[UUID, AgentRunStatusResponse] = {}

    async def upsert_user(self, user_id: UUID, email: str) -> None:
        self.users[user_id] = email

    async def store_gmail_tokens(self, user_id: UUID, tokens: GmailTokens) -> None:
        self.tokens[user_id] = tokens

    async def fetch_gmail_tokens(self, user_id: UUID) -> GmailTokens | None:
        return self.tokens.get(user_id)

    async def upsert_email(self, user_id: UUID, payload: EmailItem) -> None:
        self.emails[payload.id] = payload

    async def record_agent_run(
        self,
        run_id: UUID,
        user_id: UUID,
        email_id: UUID,
        status: str,
        result_payload: dict | None = None,
        error_message: str | None = None,
        batch_run_id: UUID | None = None,
    ) -> None:
        self.agent_runs[run_id] = AgentRunStatusResponse(
            run_id=run_id,
            status=status,
            result_payload=result_payload,
            updated_at=datetime.now(timezone.utc),
            error_message=error_message,
        )

    async def fetch_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        return self.agent_runs.get(run_id)


class FakeGmailService:
    def __init__(self) -> None:
        self.generated_state: list[str] = []
        self.labels: list[tuple[str, str]] = []
        self._tokens = GmailTokens(
            access_token=SecretStr("access-token"),
            refresh_token=SecretStr("refresh-token"),
            expires_at=datetime.now(timezone.utc),
        )

    async def create_authorization_url(self, state: str, user_id: str) -> str:
        self.generated_state.append(state)
        return f"https://example.com/oauth?state={state}"

    async def exchange_code_for_tokens(self, code: str) -> GmailTokens:
        return self._tokens

    async def list_messages(
        self, tokens: GmailTokens, user_id: str, max_results: int = 20, query: str | None = None
    ) -> list[dict]:
        return [
            {
                "id": "msg-1",
                "threadId": "thread-1",
                "snippet": "Welcome to the test inbox",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Test Message"},
                        {"name": "Date", "value": datetime.now(timezone.utc).isoformat()},
                    ]
                },
            }
        ]

    async def apply_label(
        self, message_id: str, label_id: str, tokens: GmailTokens, user_id: str
    ) -> None:
        self.labels.append((message_id, label_id))


class FakeEmailService:
    def __init__(self) -> None:
        self._email = EmailItem(
            id=uuid4(),
            gmail_message_id="msg-1",
            thread_id="thread-1",
            subject="Test Message",
            snippet="Welcome to the test inbox",
            received_at=datetime.now(timezone.utc),
        )

    async def fetch_latest_emails(
        self, user_id: UUID, max_results: int = 20, query: str | None = None
    ) -> list[EmailItem]:
        return [self._email]


class FakeLabelService:
    async def apply_label(self, request: ApplyLabelRequest) -> ApplyLabelResponse:
        return ApplyLabelResponse(success=True, label=request.label_name)


class FakeAgentService:
    def __init__(self) -> None:
        self.latest_run_id = uuid4()

    async def trigger_agent_run(self, request: AgentRunRequest) -> AgentRunResponse:
        return AgentRunResponse(run_id=self.latest_run_id, status="queued")

    async def get_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        return AgentRunStatusResponse(
            run_id=run_id,
            status="completed",
            result_payload={"summary": "done"},
            updated_at=datetime.now(timezone.utc),
            error_message=None,
        )


@pytest.fixture
def fake_db_service() -> FakeDBService:
    return FakeDBService()


# Keep old name as alias so any tests using fake_supabase still work
@pytest.fixture
def fake_supabase() -> FakeDBService:
    return FakeDBService()


@pytest.fixture
def fake_gmail_service() -> FakeGmailService:
    return FakeGmailService()


@pytest.fixture
def fake_email_service() -> FakeEmailService:
    return FakeEmailService()


@pytest.fixture
def fake_label_service() -> FakeLabelService:
    return FakeLabelService()


@pytest.fixture
def fake_agent_service() -> FakeAgentService:
    return FakeAgentService()


@pytest.fixture
def client(
    fake_supabase: FakeDBService,
    fake_gmail_service: FakeGmailService,
    fake_email_service: FakeEmailService,
    fake_label_service: FakeLabelService,
    fake_agent_service: FakeAgentService,
) -> Iterator[TestClient]:
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": "test-jwt-secret-do-not-use-in-prod",
            "AGENT_RUNTIME_BASE_URL": "http://localhost:9000",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:3005/oauth/callback",
            "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
        }
    )
    app = create_app(settings)

    app.dependency_overrides[get_db_service] = lambda: fake_supabase
    app.dependency_overrides[get_gmail_service] = lambda: fake_gmail_service
    app.dependency_overrides[get_email_service] = lambda: fake_email_service
    app.dependency_overrides[get_label_service] = lambda: fake_label_service
    app.dependency_overrides[get_agent_service] = lambda: fake_agent_service

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


TEST_JWT_SECRET = "test-jwt-secret-do-not-use-in-prod"


@pytest.fixture
def auth_user_id() -> UUID:
    """A stable user UUID for use in auth-protected tests."""
    return UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def auth_headers(auth_user_id: UUID) -> dict[str, str]:
    """Bearer token headers for auth-protected endpoint tests."""
    token = create_access_token(auth_user_id, TEST_JWT_SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def authed_client(
    fake_supabase: FakeDBService,
    fake_gmail_service: FakeGmailService,
    fake_email_service: FakeEmailService,
    fake_label_service: FakeLabelService,
    fake_agent_service: FakeAgentService,
    auth_user_id: UUID,
) -> Iterator[TestClient]:
    """TestClient with auth dependency pre-wired to a known user_id."""
    settings = Settings.model_validate(
        {
            "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
            "FERNET_SECRET_KEY": Fernet.generate_key().decode(),
            "JWT_SECRET_KEY": TEST_JWT_SECRET,
            "AGENT_RUNTIME_BASE_URL": "http://localhost:9000",
            "GOOGLE_OAUTH_CLIENT_ID": "client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "client-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:3005/oauth/callback",
            "GOOGLE_OAUTH_SCOPE": "https://www.googleapis.com/auth/gmail.modify",
        }
    )
    app = create_app(settings)

    app.dependency_overrides[get_db_service] = lambda: fake_supabase
    app.dependency_overrides[get_gmail_service] = lambda: fake_gmail_service
    app.dependency_overrides[get_email_service] = lambda: fake_email_service
    app.dependency_overrides[get_label_service] = lambda: fake_label_service
    app.dependency_overrides[get_agent_service] = lambda: fake_agent_service
    # Override auth to return a known user_id — no token needed in tests
    app.dependency_overrides[get_current_user] = lambda: auth_user_id

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
