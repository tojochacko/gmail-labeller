"""SQLAlchemy ORM models — one per database table."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.types import JSON

from .base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    email = Column(String(255), nullable=False, unique=True)
    created_at = Column(String(50), default=lambda: datetime.now(timezone.utc).isoformat())


class GmailToken(Base):
    __tablename__ = "gmail_tokens"

    user_id = Column(String(36), primary_key=True)
    access_token = Column(Text, nullable=False)   # Fernet-encrypted
    refresh_token = Column(Text, nullable=False)  # Fernet-encrypted
    expires_at = Column(String(50), nullable=False)  # ISO-8601 string
    scope = Column(String(500), nullable=True)
    token_type = Column(String(50), default="Bearer")
    id_token = Column(Text, nullable=True)  # Fernet-encrypted when present


class Email(Base):
    __tablename__ = "emails"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    gmail_message_id = Column(String(255), nullable=False)
    thread_id = Column(String(255), nullable=False, default="")
    subject = Column(Text, nullable=False, default="")
    snippet = Column(Text, nullable=True)
    sender_email = Column(String(255), nullable=True)
    sender_domain = Column(String(255), nullable=True)
    received_at = Column(String(50), nullable=False)   # ISO-8601 string
    processed_at = Column(String(50), nullable=True)
    session_id = Column(String(36), nullable=True)


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), nullable=False)
    email_id = Column(String(36), nullable=False)
    status = Column(String(50), nullable=False)
    result_payload = Column(JSON, nullable=True)
    batch_run_id = Column(String(36), nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(String(50), nullable=True)


class LabelPattern(Base):
    __tablename__ = "label_patterns"

    pattern_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False, index=True)
    label_type = Column(String(50), nullable=False)
    pattern_type = Column(String(50), nullable=False)
    pattern_value = Column(String(500), nullable=False)
    confidence_score = Column(Float, default=0.5)
    pattern_weight = Column(Float, default=1.0)
    occurrence_count = Column(Integer, default=1)
    times_applied = Column(Integer, default=0)
    times_corrected = Column(Integer, default=0)
    is_user_defined = Column(Boolean, default=False)
    last_seen_at = Column(String(50), nullable=True)
    last_applied_at = Column(String(50), nullable=True)
    created_at = Column(String(50), nullable=True)
    updated_at = Column(String(50), nullable=True)


class ClassificationSession(Base):
    __tablename__ = "classification_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = Column(String(36), nullable=False)
    status = Column(String(50), default="pending")
    email_count = Column(Integer, nullable=True)
    completed_at = Column(String(50), nullable=True)
    created_at = Column(
        String(50), default=lambda: datetime.now(timezone.utc).isoformat()
    )
