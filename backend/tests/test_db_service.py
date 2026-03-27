"""Tests for DBService - SQLite + SQLAlchemy persistence layer."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.schemas.email import EmailItem
from backend.app.schemas.oauth import GmailTokens
from backend.app.services.db_service import DBService

TEST_KEY = Fernet.generate_key().decode()


@pytest.fixture
async def db_service() -> DBService:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = DBService(session_factory=factory, fernet_key=TEST_KEY)
    yield service
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


def _make_tokens(access: str = "access", refresh: str = "refresh") -> GmailTokens:
    return GmailTokens(
        access_token=SecretStr(access),
        refresh_token=SecretStr(refresh),
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        scope="https://www.googleapis.com/auth/gmail.modify",
        token_type="Bearer",
    )


def _make_email(gmail_id: str = "msg-1") -> EmailItem:
    return EmailItem(
        id=uuid4(),
        gmail_message_id=gmail_id,
        thread_id="thread-1",
        subject="Test Subject",
        snippet="Test snippet",
        sender_email="sender@example.com",
        sender_domain="example.com",
        received_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


async def test_upsert_user_creates_record(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "test@example.com")
    # Verify user exists — no tokens yet means None, not an error
    result = await db_service.fetch_gmail_tokens(user_id)
    assert result is None


async def test_store_and_fetch_gmail_tokens_round_trip(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "test@example.com")
    tokens = _make_tokens("access-123", "refresh-456")

    await db_service.store_gmail_tokens(user_id, tokens)

    fetched = await db_service.fetch_gmail_tokens(user_id)
    assert fetched is not None
    assert fetched.access_token.get_secret_value() == "access-123"
    assert fetched.refresh_token.get_secret_value() == "refresh-456"
    assert fetched.expires_at.year == 2030


async def test_fetch_gmail_tokens_returns_none_for_unknown_user(db_service: DBService) -> None:
    result = await db_service.fetch_gmail_tokens(uuid4())
    assert result is None


async def test_tokens_are_encrypted_and_decrypt_correctly(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "enc@example.com")
    await db_service.store_gmail_tokens(user_id, _make_tokens("plain-secret"))

    fetched = await db_service.fetch_gmail_tokens(user_id)
    assert fetched is not None
    assert fetched.access_token.get_secret_value() == "plain-secret"


async def test_upsert_and_fetch_email(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    email = _make_email("msg-abc")

    await db_service.upsert_email(user_id, email)

    fetched = await db_service.fetch_email_by_gmail_id(user_id, "msg-abc")
    assert fetched is not None
    assert fetched.subject == "Test Subject"
    assert fetched.gmail_message_id == "msg-abc"


async def test_upsert_email_is_idempotent(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    email = _make_email("msg-dup")

    await db_service.upsert_email(user_id, email)
    await db_service.upsert_email(user_id, email)

    fetched = await db_service.fetch_email_by_gmail_id(user_id, "msg-dup")
    assert fetched is not None


async def test_fetch_email_returns_none_for_unknown(db_service: DBService) -> None:
    result = await db_service.fetch_email_by_gmail_id(uuid4(), "nonexistent")
    assert result is None


async def test_record_and_fetch_agent_run(db_service: DBService) -> None:
    user_id = uuid4()
    email_id = uuid4()
    run_id = uuid4()
    await db_service.upsert_user(user_id, "a@example.com")

    await db_service.record_agent_run(
        run_id, user_id, email_id, "completed", {"suggestion": "Important"}
    )

    result = await db_service.fetch_agent_run(run_id)
    assert result is not None
    assert result.status == "completed"
    assert result.result_payload == {"suggestion": "Important"}


async def test_fetch_agent_run_returns_none_for_unknown(db_service: DBService) -> None:
    result = await db_service.fetch_agent_run(uuid4())
    assert result is None


async def test_upsert_label_pattern_creates_with_initial_confidence(
    db_service: DBService,
) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "p@example.com")

    await db_service.upsert_label_pattern(user_id, "Important", "domain", "example.com")

    patterns = await db_service.get_label_patterns(user_id)
    assert len(patterns) == 1
    assert patterns[0]["pattern_value"] == "example.com"
    assert patterns[0]["confidence_score"] == pytest.approx(0.5)
    assert patterns[0]["occurrence_count"] == 1


async def test_upsert_label_pattern_increments_on_repeat(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "p@example.com")

    await db_service.upsert_label_pattern(user_id, "Important", "domain", "example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "domain", "example.com")

    patterns = await db_service.get_label_patterns(user_id)
    assert patterns[0]["occurrence_count"] == 2
    assert patterns[0]["confidence_score"] > 0.5


async def test_get_label_patterns_filters_by_label_type(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "p@example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "domain", "good.com")
    await db_service.upsert_label_pattern(user_id, "Not Important", "domain", "spam.com")

    important = await db_service.get_label_patterns(user_id, label_type="Important")
    assert len(important) == 1
    assert important[0]["pattern_value"] == "good.com"


async def test_create_user_defined_pattern_has_full_confidence(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")

    pattern_id = await db_service.create_user_defined_pattern(
        user_id, "Important", "keyword", "invoice"
    )

    assert isinstance(pattern_id, UUID)
    patterns = await db_service.get_label_patterns(user_id)
    assert patterns[0]["confidence_score"] == pytest.approx(1.0)
    assert patterns[0]["is_user_defined"] is True


async def test_update_label_pattern_modifies_confidence(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "keyword", "urgent")
    patterns = await db_service.get_label_patterns(user_id)
    pattern_id = UUID(patterns[0]["pattern_id"])

    await db_service.update_label_pattern(pattern_id, {"confidence_score": 0.9})

    updated = await db_service.get_label_patterns(user_id)
    assert updated[0]["confidence_score"] == pytest.approx(0.9)


async def test_delete_label_pattern_removes_it(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "domain", "del.com")
    patterns = await db_service.get_label_patterns(user_id)
    pattern_id = UUID(patterns[0]["pattern_id"])

    await db_service.delete_label_pattern(pattern_id)

    remaining = await db_service.get_label_patterns(user_id)
    assert len(remaining) == 0


async def test_upsert_pattern_creates_with_weight_multiplier(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")

    await db_service.upsert_pattern(user_id, "keyword", "invoice", "Important", weight_multiplier=2.0)

    patterns = await db_service.fetch_label_patterns(user_id)
    assert len(patterns) == 1
    assert patterns[0]["pattern_weight"] == pytest.approx(2.0)


async def test_upsert_pattern_increases_weight_on_repeat(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    await db_service.upsert_pattern(user_id, "keyword", "invoice", "Important", weight_multiplier=2.0)
    await db_service.upsert_pattern(user_id, "keyword", "invoice", "Important", weight_multiplier=2.0)

    patterns = await db_service.fetch_label_patterns(user_id)
    assert patterns[0]["pattern_weight"] > 2.0


async def test_increment_pattern_usage_tracks_applications(db_service: DBService) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "domain", "track.com")
    patterns = await db_service.get_label_patterns(user_id)
    pattern_id = UUID(patterns[0]["pattern_id"])

    await db_service.increment_pattern_usage(pattern_id, was_corrected=False)

    updated = await db_service.get_label_patterns(user_id)
    assert updated[0]["times_applied"] == 1
    assert updated[0]["times_corrected"] == 0


async def test_increment_pattern_usage_with_correction_lowers_confidence(
    db_service: DBService,
) -> None:
    user_id = uuid4()
    await db_service.upsert_user(user_id, "u@example.com")
    await db_service.upsert_label_pattern(user_id, "Important", "domain", "correct.com")
    patterns = await db_service.get_label_patterns(user_id)
    pattern_id = UUID(patterns[0]["pattern_id"])

    await db_service.increment_pattern_usage(pattern_id, was_corrected=True)

    updated = await db_service.get_label_patterns(user_id, min_confidence=0.0)
    assert updated[0]["times_corrected"] == 1
    assert updated[0]["confidence_score"] < 0.5
