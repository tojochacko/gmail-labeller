"""SQLite + SQLAlchemy persistence layer — replaces SupabaseService."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..db.models import AgentRun, Email, GmailToken, LabelPattern, User
from ..schemas.agent import AgentRunStatusResponse
from ..schemas.email import EmailItem
from ..schemas.oauth import GmailTokens

logger = logging.getLogger(__name__)


class DBService:
    """Async SQLite persistence with Fernet-encrypted token storage."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        fernet_key: str,
    ) -> None:
        self._session_factory = session_factory
        key = fernet_key.encode() if isinstance(fernet_key, str) else fernet_key
        self._cipher = Fernet(key)

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._session_factory

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    async def upsert_user(self, user_id: UUID, email: str) -> None:
        async with self._session_factory() as session:
            obj = await session.get(User, str(user_id))
            if obj is None:
                session.add(User(id=str(user_id), email=email))
            else:
                obj.email = email
            await session.commit()

    # ------------------------------------------------------------------
    # Gmail tokens
    # ------------------------------------------------------------------

    async def store_gmail_tokens(self, user_id: UUID, tokens: GmailTokens) -> None:
        encrypted_access = self._encrypt(tokens.access_token.get_secret_value())
        encrypted_refresh = self._encrypt(tokens.refresh_token.get_secret_value())
        encrypted_id = (
            self._encrypt(tokens.id_token.get_secret_value()) if tokens.id_token else None
        )
        async with self._session_factory() as session:
            obj = await session.get(GmailToken, str(user_id))
            if obj is None:
                session.add(
                    GmailToken(
                        user_id=str(user_id),
                        access_token=encrypted_access,
                        refresh_token=encrypted_refresh,
                        expires_at=tokens.expires_at.isoformat(),
                        scope=tokens.scope,
                        token_type=tokens.token_type,
                        id_token=encrypted_id,
                    )
                )
            else:
                obj.access_token = encrypted_access
                obj.refresh_token = encrypted_refresh
                obj.expires_at = tokens.expires_at.isoformat()
                obj.scope = tokens.scope
                obj.token_type = tokens.token_type
                obj.id_token = encrypted_id
            await session.commit()

    async def fetch_gmail_tokens(self, user_id: UUID) -> GmailTokens | None:
        async with self._session_factory() as session:
            obj = await session.get(GmailToken, str(user_id))
            if obj is None:
                return None
            return GmailTokens(
                access_token=SecretStr(self._decrypt(obj.access_token)),
                refresh_token=SecretStr(self._decrypt(obj.refresh_token)),
                expires_at=datetime.fromisoformat(obj.expires_at),
                scope=obj.scope,
                token_type=obj.token_type or "Bearer",
                id_token=SecretStr(self._decrypt(obj.id_token)) if obj.id_token else None,
            )

    # ------------------------------------------------------------------
    # Emails
    # ------------------------------------------------------------------

    async def upsert_email(self, user_id: UUID, payload: EmailItem) -> None:
        logger.debug(
            "Upserting email: id=%s gmail_message_id=%s subject='%s'",
            payload.id,
            payload.gmail_message_id,
            payload.subject,
        )
        async with self._session_factory() as session:
            obj = await session.get(Email, str(payload.id))
            received = payload.received_at.isoformat()
            processed = payload.processed_at.isoformat() if payload.processed_at else None
            if obj is None:
                session.add(
                    Email(
                        id=str(payload.id),
                        user_id=str(user_id),
                        gmail_message_id=payload.gmail_message_id,
                        thread_id=payload.thread_id,
                        subject=payload.subject,
                        snippet=payload.snippet,
                        sender_email=payload.sender_email,
                        sender_domain=payload.sender_domain,
                        received_at=received,
                        processed_at=processed,
                    )
                )
            else:
                obj.subject = payload.subject
                obj.snippet = payload.snippet
                obj.sender_email = payload.sender_email
                obj.sender_domain = payload.sender_domain
                obj.received_at = received
                obj.processed_at = processed
            await session.commit()

    async def fetch_email_by_gmail_id(
        self, user_id: UUID, gmail_message_id: str
    ) -> EmailItem | None:
        async with self._session_factory() as session:
            stmt = select(Email).where(
                Email.user_id == str(user_id),
                Email.gmail_message_id == gmail_message_id,
            )
            result = await session.execute(stmt)
            obj = result.scalar_one_or_none()
            if obj is None:
                return None
            return EmailItem(
                id=UUID(obj.id),
                gmail_message_id=obj.gmail_message_id,
                thread_id=obj.thread_id or "",
                subject=obj.subject or "",
                snippet=obj.snippet,
                sender_email=obj.sender_email,
                sender_domain=obj.sender_domain,
                received_at=datetime.fromisoformat(obj.received_at),
                processed_at=datetime.fromisoformat(obj.processed_at) if obj.processed_at else None,
            )

    # ------------------------------------------------------------------
    # Agent runs
    # ------------------------------------------------------------------

    async def record_agent_run(
        self,
        run_id: UUID,
        user_id: UUID,
        email_id: UUID,
        status: str,
        result_payload: Optional[dict] = None,
        error_message: Optional[str] = None,
        batch_run_id: Optional[UUID] = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_factory() as session:
            obj = await session.get(AgentRun, str(run_id))
            if obj is None:
                session.add(
                    AgentRun(
                        id=str(run_id),
                        user_id=str(user_id),
                        email_id=str(email_id),
                        status=status,
                        result_payload=result_payload,
                        error_message=error_message,
                        batch_run_id=str(batch_run_id) if batch_run_id else None,
                        updated_at=now,
                    )
                )
            else:
                obj.status = status
                obj.result_payload = result_payload
                obj.error_message = error_message
                obj.updated_at = now
            await session.commit()

    async def fetch_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        async with self._session_factory() as session:
            obj = await session.get(AgentRun, str(run_id))
            if obj is None:
                return None
            updated = (
                datetime.fromisoformat(obj.updated_at)
                if obj.updated_at
                else datetime.now(timezone.utc)
            )
            return AgentRunStatusResponse(
                run_id=UUID(obj.id),
                status=obj.status,
                result_payload=obj.result_payload,
                updated_at=updated,
                error_message=obj.error_message,
            )

    # ------------------------------------------------------------------
    # Label patterns
    # ------------------------------------------------------------------

    async def upsert_label_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> None:
        """Insert a new pattern or increment its occurrence count."""
        async with self._session_factory() as session:
            stmt = select(LabelPattern).where(
                LabelPattern.user_id == str(user_id),
                LabelPattern.label_type == label_type,
                LabelPattern.pattern_type == pattern_type,
                LabelPattern.pattern_value == pattern_value,
            )
            result = await session.execute(stmt)
            obj = result.scalar_one_or_none()
            now = datetime.now(timezone.utc).isoformat()

            if obj is None:
                session.add(
                    LabelPattern(
                        pattern_id=str(uuid4()),
                        user_id=str(user_id),
                        label_type=label_type,
                        pattern_type=pattern_type,
                        pattern_value=pattern_value,
                        confidence_score=0.5,
                        occurrence_count=1,
                        last_seen_at=now,
                        is_user_defined=False,
                    )
                )
            else:
                new_count = obj.occurrence_count + 1
                obj.occurrence_count = new_count
                obj.confidence_score = min(1.0, 0.5 + (new_count * 0.1))
                obj.last_seen_at = now
            await session.commit()

    async def get_label_patterns(
        self,
        user_id: UUID,
        label_type: Optional[str] = None,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.3,
    ) -> list[dict]:
        async with self._session_factory() as session:
            stmt = (
                select(LabelPattern)
                .where(
                    LabelPattern.user_id == str(user_id),
                    LabelPattern.confidence_score >= min_confidence,
                )
                .order_by(LabelPattern.confidence_score.desc())
            )
            if label_type:
                stmt = stmt.where(LabelPattern.label_type == label_type)
            if pattern_type:
                stmt = stmt.where(LabelPattern.pattern_type == pattern_type)
            result = await session.execute(stmt)
            return [self._pattern_to_dict(row) for row in result.scalars().all()]

    async def create_user_defined_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> UUID:
        pattern_id = uuid4()
        async with self._session_factory() as session:
            session.add(
                LabelPattern(
                    pattern_id=str(pattern_id),
                    user_id=str(user_id),
                    label_type=label_type,
                    pattern_type=pattern_type,
                    pattern_value=pattern_value.strip().lower(),
                    confidence_score=1.0,
                    occurrence_count=1,
                    is_user_defined=True,
                )
            )
            await session.commit()
        return pattern_id

    async def update_label_pattern(self, pattern_id: UUID, updates: dict[str, Any]) -> None:
        async with self._session_factory() as session:
            stmt = (
                update(LabelPattern)
                .where(LabelPattern.pattern_id == str(pattern_id))
                .values(**updates)
            )
            await session.execute(stmt)
            await session.commit()

    async def delete_label_pattern(self, pattern_id: UUID) -> None:
        async with self._session_factory() as session:
            stmt = delete(LabelPattern).where(LabelPattern.pattern_id == str(pattern_id))
            await session.execute(stmt)
            await session.commit()

    async def fetch_label_patterns(self, user_id: UUID) -> list[dict]:
        """Fetch all patterns for a user ordered by weight then confidence (for auto-labeling)."""
        async with self._session_factory() as session:
            stmt = (
                select(LabelPattern)
                .where(LabelPattern.user_id == str(user_id))
                .order_by(
                    LabelPattern.pattern_weight.desc(),
                    LabelPattern.confidence_score.desc(),
                )
            )
            result = await session.execute(stmt)
            return [self._pattern_to_dict(row) for row in result.scalars().all()]

    async def upsert_pattern(
        self,
        user_id: UUID,
        pattern_type: str,
        pattern_value: str,
        label_type: str,
        weight_multiplier: float = 1.0,
    ) -> None:
        """Create or update a pattern with a weight multiplier (used for re-mark learning)."""
        value = pattern_value.lower().strip()
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_factory() as session:
            stmt = select(LabelPattern).where(
                LabelPattern.user_id == str(user_id),
                LabelPattern.pattern_type == pattern_type,
                LabelPattern.pattern_value == value,
                LabelPattern.label_type == label_type,
            )
            result = await session.execute(stmt)
            obj = result.scalar_one_or_none()

            if obj is not None:
                current = obj.pattern_weight or 1.0
                obj.pattern_weight = min(current + weight_multiplier - 1.0, 5.0)
                obj.occurrence_count = (obj.occurrence_count or 0) + 1
                obj.last_seen_at = now
                obj.updated_at = now
            else:
                session.add(
                    LabelPattern(
                        pattern_id=str(uuid4()),
                        user_id=str(user_id),
                        label_type=label_type,
                        pattern_type=pattern_type,
                        pattern_value=value,
                        confidence_score=0.5,
                        pattern_weight=weight_multiplier,
                        occurrence_count=1,
                        is_user_defined=False,
                        times_applied=0,
                        times_corrected=0,
                        last_seen_at=now,
                        created_at=now,
                        updated_at=now,
                    )
                )
            await session.commit()

    async def increment_pattern_usage(
        self, pattern_id: UUID, was_corrected: bool = False
    ) -> None:
        """Track pattern usage and update confidence based on correction rate."""
        now = datetime.now(timezone.utc).isoformat()
        async with self._session_factory() as session:
            obj = await session.get(LabelPattern, str(pattern_id))
            if obj is None:
                logger.warning("Pattern %s not found for usage update", pattern_id)
                return
            times_applied = (obj.times_applied or 0) + 1
            times_corrected = (obj.times_corrected or 0) + (1 if was_corrected else 0)
            success_rate = (times_applied - times_corrected) / times_applied
            old_confidence = obj.confidence_score or 0.5
            new_confidence = round((success_rate * 0.7) + (old_confidence * 0.3), 2)
            obj.times_applied = times_applied
            obj.times_corrected = times_corrected
            obj.confidence_score = new_confidence
            obj.last_applied_at = now
            obj.updated_at = now
            await session.commit()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pattern_to_dict(self, obj: LabelPattern) -> dict:
        return {
            "pattern_id": obj.pattern_id,
            "user_id": obj.user_id,
            "label_type": obj.label_type,
            "pattern_type": obj.pattern_type,
            "pattern_value": obj.pattern_value,
            "confidence_score": obj.confidence_score,
            "pattern_weight": obj.pattern_weight or 1.0,
            "occurrence_count": obj.occurrence_count,
            "times_applied": obj.times_applied or 0,
            "times_corrected": obj.times_corrected or 0,
            "is_user_defined": bool(obj.is_user_defined),
            "last_seen_at": obj.last_seen_at,
            "last_applied_at": obj.last_applied_at,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }

    def _encrypt(self, plaintext: str) -> str:
        return self._cipher.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext.encode()).decode()
