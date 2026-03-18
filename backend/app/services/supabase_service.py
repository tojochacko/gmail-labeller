"""Supabase persistence helpers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import logging

from cryptography.fernet import Fernet
from pydantic import SecretStr
from supabase import Client, create_client

from ..config import Settings
from ..schemas.agent import AgentRunStatusResponse
from ..schemas.email import EmailItem
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)


class SupabaseService:
    """Lightweight wrapper around supabase-py with encryption support."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: Optional[Client] = None
        self._cipher = Fernet(settings.fernet_secret_key.get_secret_value().encode())

    @property
    def client(self) -> Client:
        if self._client is None:
            url = str(self._settings.supabase_url)
            service_key = self._settings.supabase_service_role_key.get_secret_value()
            self._client = create_client(url, service_key)
        return self._client

    async def upsert_user(self, user_id: UUID, email: str) -> None:
        payload = {
            "id": str(user_id),
            "email": email,
        }
        await self._execute("users", "upsert", payload)

    async def store_gmail_tokens(self, user_id: UUID, tokens: GmailTokens) -> None:
        payload = {
            "user_id": str(user_id),
            "access_token": self._encrypt(tokens.access_token.get_secret_value()),
            "refresh_token": self._encrypt(tokens.refresh_token.get_secret_value()),
            "expires_at": tokens.expires_at.isoformat(),
            "scope": tokens.scope,
            "token_type": tokens.token_type,
            "id_token": self._encrypt(tokens.id_token.get_secret_value())
            if tokens.id_token
            else None,
        }
        await self._execute("gmail_tokens", "upsert", payload)

    async def fetch_gmail_tokens(self, user_id: UUID) -> GmailTokens | None:
        result = await self._query("gmail_tokens", {"user_id": str(user_id)})
        if not result:
            return None
        row = result[0]
        expires_at = datetime.fromisoformat(row["expires_at"])
        return GmailTokens(
            access_token=SecretStr(self._decrypt(row["access_token"])),
            refresh_token=SecretStr(self._decrypt(row["refresh_token"])),
            expires_at=expires_at,
            scope=row.get("scope"),
            token_type=row.get("token_type", "Bearer"),
            id_token=SecretStr(self._decrypt(row["id_token"])) if row.get("id_token") else None,
        )

    async def upsert_email(self, user_id: UUID, payload: EmailItem) -> None:
        """Upsert email to database.

        Args:
            user_id: User UUID
            payload: Email item to upsert
        """
        logger.debug(
            f"💾 Upserting email: id={payload.id}, gmail_message_id={payload.gmail_message_id}, "
            f"subject='{payload.subject}'"
        )

        try:
            # Use mode='json' to serialize UUIDs and datetimes to JSON-compatible strings
            # Exclude gmail_labels — it's a transient field not persisted in the DB
            record = payload.model_dump(mode="json", exclude={"gmail_labels"})
            record["user_id"] = str(user_id)

            logger.debug(f"Upsert record keys: {list(record.keys())}")

            await self._execute("emails", "upsert", record)

            logger.info(
                f"✅ Email upserted successfully: id={payload.id}, "
                f"gmail_message_id={payload.gmail_message_id}"
            )

        except Exception as e:
            logger.error(
                f"❌ Error upserting email: id={payload.id}, error={str(e)}", exc_info=True
            )
            raise

    async def fetch_email_by_gmail_id(
        self, user_id: UUID, gmail_message_id: str
    ) -> EmailItem | None:
        """Fetch email by Gmail message ID.

        Args:
            user_id: User UUID
            gmail_message_id: Gmail message identifier

        Returns:
            EmailItem if found, None otherwise
        """
        logger.debug(
            f"🔍 Fetching email from DB: user_id={user_id}, gmail_message_id={gmail_message_id}"
        )

        try:
            response = (
                self.client.table("emails")
                .select("*")
                .eq("user_id", str(user_id))
                .eq("gmail_message_id", gmail_message_id)
                .execute()
            )

            logger.debug(
                f"Supabase query response: data length={len(response.data) if response.data else 0}"
            )

            if response.data:
                email_data = response.data[0]
                logger.info(
                    f"✅ Email found in database: id={email_data.get('id')}, "
                    f"subject='{email_data.get('subject')}'"
                )
                return EmailItem(**email_data)
            else:
                logger.debug(f"❌ Email {gmail_message_id} not found in database")
                return None

        except Exception as e:
            logger.error(
                f"❌ Error fetching email from database: gmail_message_id={gmail_message_id}, "
                f"error={str(e)}",
                exc_info=True,
            )
            return None

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
        record: dict[str, Any] = {
            "id": str(run_id),
            "user_id": str(user_id),
            "email_id": str(email_id),
            "status": status,
            "result_payload": result_payload,
            "error_message": error_message,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if batch_run_id is not None:
            record["batch_run_id"] = str(batch_run_id)
        await self._execute("agent_runs", "upsert", record)

    async def fetch_agent_run(self, run_id: UUID) -> AgentRunStatusResponse | None:
        result = await self._query("agent_runs", {"id": str(run_id)})
        if not result:
            return None
        row = result[0]
        return AgentRunStatusResponse(
            run_id=UUID(row["id"]),
            status=row["status"],
            result_payload=row.get("result_payload"),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            error_message=row.get("error_message"),
        )

    # ============================================
    # Label Patterns Methods (AI Learning)
    # ============================================

    async def upsert_label_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> None:
        """Insert or update a label pattern (increment occurrence)."""
        try:
            # Check if pattern exists
            response = await asyncio.to_thread(
                self._query_pattern_sync, user_id, label_type, pattern_type, pattern_value
            )

            now = datetime.now(timezone.utc)

            if response:
                # Pattern exists - increment occurrence count
                existing = response[0]
                new_count = existing["occurrence_count"] + 1
                # Increase confidence with occurrences (cap at 1.0)
                new_confidence = min(1.0, 0.5 + (new_count * 0.1))

                await asyncio.to_thread(
                    self._update_pattern_sync,
                    existing["pattern_id"],
                    {
                        "occurrence_count": new_count,
                        "confidence_score": new_confidence,
                        "last_seen_at": now.isoformat(),
                    },
                )
            else:
                # New pattern - insert
                await asyncio.to_thread(
                    self._insert_pattern_sync,
                    {
                        "user_id": str(user_id),
                        "label_type": label_type,
                        "pattern_type": pattern_type,
                        "pattern_value": pattern_value,
                        "confidence_score": 0.5,  # Initial confidence
                        "occurrence_count": 1,
                        "last_seen_at": now.isoformat(),
                        "is_user_defined": False,
                    },
                )

        except Exception as e:
            logger.error(f"Error upserting label pattern: {e}")
            raise

    def _query_pattern_sync(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> list[dict]:
        """Sync method to query for existing pattern."""
        response = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", str(user_id))
            .eq("label_type", label_type)
            .eq("pattern_type", pattern_type)
            .eq("pattern_value", pattern_value)
            .execute()
        )
        return response.data or []

    def _update_pattern_sync(self, pattern_id: str, updates: dict) -> None:
        """Sync method to update a pattern."""
        self.client.table("label_patterns").update(updates).eq("pattern_id", pattern_id).execute()

    def _insert_pattern_sync(self, payload: dict) -> None:
        """Sync method to insert a new pattern."""
        self.client.table("label_patterns").insert(payload).execute()

    async def get_label_patterns(
        self,
        user_id: UUID,
        label_type: Optional[str] = None,
        pattern_type: Optional[str] = None,
        min_confidence: float = 0.3,
    ) -> list[dict]:
        """
        Retrieve label patterns for a user with optional filters.

        Args:
            user_id: User ID
            label_type: Optional filter for "Important" or "Not Important"
            pattern_type: Optional filter for "domain" or "keyword"
            min_confidence: Minimum confidence score (default 0.3)

        Returns:
            List of pattern dictionaries
        """
        try:
            return await asyncio.to_thread(
                self._get_patterns_sync, user_id, label_type, pattern_type, min_confidence
            )
        except Exception as e:
            logger.error(f"Error retrieving label patterns: {e}")
            raise

    def _get_patterns_sync(
        self,
        user_id: UUID,
        label_type: Optional[str],
        pattern_type: Optional[str],
        min_confidence: float,
    ) -> list[dict]:
        """Sync method to get label patterns."""
        query = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", str(user_id))
            .gte("confidence_score", min_confidence)
            .order("confidence_score", desc=True)
        )

        if label_type:
            query = query.eq("label_type", label_type)
        if pattern_type:
            query = query.eq("pattern_type", pattern_type)

        response = query.execute()
        return response.data or []

    async def create_user_defined_pattern(
        self,
        user_id: UUID,
        label_type: str,
        pattern_type: str,
        pattern_value: str,
    ) -> UUID:
        """
        Create a user-defined pattern.

        Args:
            user_id: User ID
            label_type: "Important" or "Not Important"
            pattern_type: "domain" or "keyword"
            pattern_value: Pattern value

        Returns:
            UUID of created pattern
        """
        try:
            pattern_id = await asyncio.to_thread(
                self._create_user_pattern_sync,
                user_id,
                label_type,
                pattern_type,
                pattern_value,
            )
            return UUID(pattern_id)
        except Exception as e:
            logger.error(f"Error creating user-defined pattern: {e}")
            raise

    def _create_user_pattern_sync(
        self, user_id: UUID, label_type: str, pattern_type: str, pattern_value: str
    ) -> str:
        """Sync method to create user-defined pattern."""
        response = (
            self.client.table("label_patterns")
            .insert(
                {
                    "user_id": str(user_id),
                    "label_type": label_type,
                    "pattern_type": pattern_type,
                    "pattern_value": pattern_value.strip().lower(),
                    "confidence_score": 1.0,  # User-defined = high confidence
                    "occurrence_count": 1,
                    "is_user_defined": True,
                }
            )
            .execute()
        )
        return str(response.data[0]["pattern_id"])

    async def update_label_pattern(self, pattern_id: UUID, updates: dict) -> None:
        """
        Update a label pattern.

        Args:
            pattern_id: Pattern ID
            updates: Dictionary of fields to update
        """
        try:
            await asyncio.to_thread(self._update_pattern_sync, str(pattern_id), updates)
        except Exception as e:
            logger.error(f"Error updating label pattern: {e}")
            raise

    async def delete_label_pattern(self, pattern_id: UUID) -> None:
        """
        Delete a label pattern.

        Args:
            pattern_id: Pattern ID
        """
        try:
            await asyncio.to_thread(self._delete_pattern_sync, str(pattern_id))
        except Exception as e:
            logger.error(f"Error deleting label pattern: {e}")
            raise

    def _delete_pattern_sync(self, pattern_id: str) -> None:
        """Sync method to delete a pattern."""
        self.client.table("label_patterns").delete().eq("pattern_id", pattern_id).execute()

    # ============================================
    # NEW: Auto-Labeling Engine Support Methods
    # ============================================

    async def fetch_label_patterns(self, user_id: UUID) -> list[dict]:
        """Fetch all label patterns for a user (for auto-labeling).

        Returns raw dictionaries for use in auto-labeling engine.

        Args:
            user_id: User UUID

        Returns:
            List of pattern dictionaries with all fields
        """
        try:
            return await asyncio.to_thread(self._fetch_patterns_for_auto_label_sync, str(user_id))
        except Exception as e:
            logger.error(f"Error fetching patterns for auto-labeling: {e}")
            return []

    def _fetch_patterns_for_auto_label_sync(self, user_id: str) -> list[dict]:
        """Sync method to fetch patterns for auto-labeling."""
        response = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", user_id)
            .order("pattern_weight", desc=True)  # Prioritize high-weight patterns
            .order("confidence_score", desc=True)
            .execute()
        )

        if hasattr(response, "data") and response.data:
            return list(response.data)  # Cast to list to satisfy mypy
        return []

    async def upsert_pattern(
        self,
        user_id: UUID,
        pattern_type: str,
        pattern_value: str,
        label_type: str,
        weight_multiplier: float = 1.0,
    ) -> None:
        """Create or update a pattern with weight multiplier.

        Used by auto-labeling engine when learning from user re-marks.

        Args:
            user_id: User UUID
            pattern_type: Type of pattern (domain, keyword, subject)
            pattern_value: Pattern value (normalized, lowercase)
            label_type: Label type (Important, Not Important)
            weight_multiplier: Weight multiplier (e.g., 2.0 for re-marks)
        """
        try:
            await asyncio.to_thread(
                self._upsert_pattern_with_weight_sync,
                str(user_id),
                pattern_type,
                pattern_value.lower().strip(),
                label_type,
                weight_multiplier,
            )
        except Exception as e:
            logger.error(f"Error upserting pattern: {e}")
            raise

    def _upsert_pattern_with_weight_sync(
        self,
        user_id: str,
        pattern_type: str,
        pattern_value: str,
        label_type: str,
        weight_multiplier: float,
    ) -> None:
        """Sync method to upsert pattern with weight multiplier."""
        from datetime import datetime, timezone
        from uuid import uuid4

        # Check if pattern exists
        response = (
            self.client.table("label_patterns")
            .select("*")
            .eq("user_id", user_id)
            .eq("pattern_type", pattern_type)
            .eq("pattern_value", pattern_value)
            .eq("label_type", label_type)
            .execute()
        )

        now = datetime.now(timezone.utc).isoformat()

        if hasattr(response, "data") and response.data:
            # Update existing pattern
            existing = response.data[0]
            pattern_id = existing["pattern_id"]

            # Increase weight (cap at 5.0)
            current_weight = existing.get("pattern_weight", 1.0)
            new_weight = min(current_weight + weight_multiplier - 1.0, 5.0)

            # Increment occurrence count
            occurrence_count = existing.get("occurrence_count", 0) + 1

            self.client.table("label_patterns").update(
                {
                    "pattern_weight": new_weight,
                    "occurrence_count": occurrence_count,
                    "last_seen_at": now,
                    "updated_at": now,
                }
            ).eq("pattern_id", pattern_id).execute()

            logger.debug(
                f"Updated pattern {pattern_id}: weight {current_weight:.1f} → {new_weight:.1f}"
            )
        else:
            # Create new pattern
            pattern_id = uuid4()

            self.client.table("label_patterns").insert(
                {
                    "pattern_id": str(pattern_id),
                    "user_id": user_id,
                    "label_type": label_type,
                    "pattern_type": pattern_type,
                    "pattern_value": pattern_value,
                    "confidence_score": 0.5,  # Initial confidence
                    "pattern_weight": weight_multiplier,
                    "occurrence_count": 1,
                    "is_user_defined": False,
                    "last_seen_at": now,
                    "times_applied": 0,
                    "times_corrected": 0,
                    "created_at": now,
                    "updated_at": now,
                }
            ).execute()

            logger.debug(
                f"Created new pattern: {pattern_type}='{pattern_value}' → {label_type} "
                f"(weight={weight_multiplier:.1f})"
            )

    async def increment_pattern_usage(
        self,
        pattern_id: UUID,
        was_corrected: bool = False,
    ) -> None:
        """Increment pattern usage statistics.

        Args:
            pattern_id: Pattern UUID
            was_corrected: Whether the auto-label was corrected by user (re-marked)
        """
        try:
            await asyncio.to_thread(
                self._increment_pattern_usage_sync,
                str(pattern_id),
                was_corrected,
            )
        except Exception as e:
            logger.error(f"Error incrementing pattern usage: {e}")

    def _increment_pattern_usage_sync(self, pattern_id: str, was_corrected: bool) -> None:
        """Sync method to increment pattern usage."""
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()

        # Fetch current values
        response = (
            self.client.table("label_patterns")
            .select("times_applied, times_corrected, confidence_score")
            .eq("pattern_id", pattern_id)
            .execute()
        )

        if not (hasattr(response, "data") and response.data):
            logger.warning(f"Pattern {pattern_id} not found for usage update")
            return

        current = response.data[0]
        times_applied = current.get("times_applied", 0) + 1
        times_corrected = current.get("times_corrected", 0) + (1 if was_corrected else 0)

        # Calculate new confidence score based on success rate
        # confidence = (times_applied - times_corrected) / times_applied
        if times_applied > 0:
            success_rate = (times_applied - times_corrected) / times_applied
            # Blend with current confidence (70% new, 30% old)
            old_confidence = current.get("confidence_score", 0.5)
            new_confidence = (success_rate * 0.7) + (old_confidence * 0.3)
        else:
            new_confidence = current.get("confidence_score", 0.5)

        # Update database
        self.client.table("label_patterns").update(
            {
                "times_applied": times_applied,
                "times_corrected": times_corrected,
                "confidence_score": round(new_confidence, 2),
                "last_applied_at": now,
                "updated_at": now,
            }
        ).eq("pattern_id", pattern_id).execute()

        logger.debug(
            f"Pattern {pattern_id} usage: applied={times_applied}, "
            f"corrected={times_corrected}, confidence={new_confidence:.2f}"
        )


    async def _execute(self, table: str, operation: str, payload: Any) -> None:
        logger.debug("Supabase {} on {} payload={}", operation, table, payload)
        await asyncio.to_thread(self._execute_sync, table, operation, payload)

    def _execute_sync(self, table: str, operation: str, payload: Any) -> None:
        query = self.client.table(table)
        if operation == "upsert":
            query = query.upsert(payload)
        else:  # pragma: no cover - defensive branch
            raise ValueError(f"Unsupported Supabase operation: {operation}")
        query.execute()

    async def _query(self, table: str, filters: dict[str, Any]) -> list[dict]:
        logger.debug("Supabase select on {} filters={}", table, filters)
        return await asyncio.to_thread(self._query_sync, table, filters)

    def _query_sync(self, table: str, filters: dict[str, Any]) -> list[dict]:
        query = self.client.table(table).select("*")
        for key, value in filters.items():
            query = query.eq(key, value)
        response = query.limit(1).execute()
        return response.data or []

    def _encrypt(self, plaintext: str) -> str:
        return self._cipher.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext: str) -> str:
        return self._cipher.decrypt(ciphertext.encode()).decode()
