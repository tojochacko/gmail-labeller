"""Adapter layer for the Gmail API (direct Google integration)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from ..config import Settings
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)

_LABEL_MAPPING = {
    "Important": "TImportant",
    "Not Important": "TNotImportant",
}
_OPPOSITE_LABEL = {
    "TImportant": "TNotImportant",
    "TNotImportant": "TImportant",
}
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailApiAdapter:
    """Direct Gmail API adapter using google-api-python-client."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        scopes: list[str],
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._scopes = scopes

    # ── OAuth helpers ──────────────────────────────────────────────────────

    def _flow(self) -> Flow:
        config = {
            "web": {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": _TOKEN_URI,
                "redirect_uris": [self._redirect_uri],
            }
        }
        flow = Flow.from_client_config(config, scopes=self._scopes)
        flow.redirect_uri = self._redirect_uri
        return flow

    def _credentials(self, access_token: str, refresh_token: str) -> Credentials:
        return Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=_TOKEN_URI,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scopes=self._scopes,
        )

    def _service(self, access_token: str, refresh_token: str):
        creds = self._credentials(access_token, refresh_token)
        return build("gmail", "v1", credentials=creds)

    # ── Public API ─────────────────────────────────────────────────────────

    def get_authorization_url(self, state: str) -> str:
        """Return a Google OAuth2 authorization URL."""
        url, _ = self._flow().authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            state=state,
            prompt="consent",
        )
        logger.debug("Generated authorization URL (state=%s)", state)
        return url

    def exchange_code_for_tokens(self, code: str) -> dict:
        """Exchange an authorization code for OAuth tokens.

        Returns:
            Dict with access_token, refresh_token, token_type, scope.
        """
        flow = self._flow()
        flow.fetch_token(code=code)
        creds = flow.credentials
        result: dict = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
            "token_type": "Bearer",
        }
        if creds.expiry:
            result["expires_at"] = creds.expiry.isoformat()
        if creds.scopes:
            result["scope"] = " ".join(creds.scopes)
        logger.debug("Exchanged code for tokens successfully")
        return result

    def list_messages(
        self,
        access_token: str,
        refresh_token: str,
        max_results: int = 20,
        query: str | None = None,
        user_id: str | None = None,  # kept for interface compatibility, not used
    ) -> list[dict]:
        """List Gmail messages, returning full metadata for each."""
        svc = self._service(access_token, refresh_token)
        q = query or "in:inbox"

        response = (
            svc.users()
            .messages()
            .list(userId="me", q=q, maxResults=max_results)
            .execute()
        )
        message_stubs = response.get("messages", [])
        if not message_stubs:
            return []

        messages = []
        for stub in message_stubs:
            msg = (
                svc.users()
                .messages()
                .get(
                    userId="me",
                    id=stub["id"],
                    format="metadata",
                    metadataHeaders=["Subject", "From", "Date"],
                )
                .execute()
            )
            messages.append(msg)

        logger.info("Fetched %d messages", len(messages))
        return messages

    def get_message(
        self,
        message_id: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> dict | None:
        """Fetch a single Gmail message by ID."""
        try:
            svc = self._service(access_token, refresh_token)
            msg = (
                svc.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute()
            )
            logger.debug("Fetched message %s", message_id)
            return msg
        except Exception as exc:
            logger.error("Error fetching message %s: %s", message_id, exc)
            return None

    def list_labels(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> list[dict]:
        """List all Gmail labels for the authenticated user."""
        svc = self._service(access_token, refresh_token)
        response = svc.users().labels().list(userId="me").execute()
        labels = response.get("labels", [])
        logger.debug("Found %d labels", len(labels))
        return labels

    def create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Create a Gmail label and return its ID."""
        svc = self._service(access_token, refresh_token)
        body = {
            "name": label_name,
            "messageListVisibility": "show",
            "labelListVisibility": "labelShow",
        }
        result = svc.users().labels().create(userId="me", body=body).execute()
        label_id = result.get("id")
        if not label_id:
            raise RuntimeError(f"Failed to create label '{label_name}': no ID in response")
        logger.info("Created label '%s' with ID %s", label_name, label_id)
        return str(label_id)

    def get_or_create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Return existing label ID by name, or create it."""
        labels = self.list_labels(
            access_token=access_token, refresh_token=refresh_token
        )
        for label in labels:
            if label.get("name", "").lower() == label_name.lower():
                logger.debug("Found existing label '%s' = %s", label_name, label["id"])
                return str(label["id"])

        logger.info("Label '%s' not found, creating", label_name)
        return self.create_label(
            label_name=label_name,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def apply_label(
        self,
        message_id: str,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> None:
        """Apply a classification label to a Gmail message.

        Maps "Important" -> "TImportant" and "Not Important" -> "TNotImportant".
        For unrecognised label names (e.g. "ai-job-alert"), applies as-is.
        Removes the opposite classification label and INBOX to archive the email.
        """
        custom_name = _LABEL_MAPPING.get(label_name, label_name)
        logger.info("Applying label '%s' to message %s", custom_name, message_id)

        label_id = self.get_or_create_label(
            label_name=custom_name,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        remove_ids: list[str] = ["INBOX"]
        opposite_name = _OPPOSITE_LABEL.get(custom_name)
        if opposite_name:
            existing = self.list_labels(
                access_token=access_token, refresh_token=refresh_token
            )
            for lbl in existing:
                if lbl.get("name") == opposite_name:
                    remove_ids.append(lbl["id"])
                    break

        svc = self._service(access_token, refresh_token)
        body = {"addLabelIds": [label_id], "removeLabelIds": remove_ids}
        svc.users().messages().modify(userId="me", id=message_id, body=body).execute()
        logger.info("Applied '%s' to message %s", custom_name, message_id)


# ── Factory ───────────────────────────────────────────────────────────────


@dataclass
class GmailToolkitFactory:
    """Builds a GmailApiAdapter from application settings."""

    settings: Settings

    def build(self) -> GmailApiAdapter:
        return GmailApiAdapter(
            client_id=self.settings.google_oauth_client_id,
            client_secret=self.settings.google_oauth_client_secret.get_secret_value(),
            redirect_uri=str(self.settings.google_oauth_redirect_uri),
            scopes=[self.settings.google_oauth_scope],
        )


# ── Service (domain logic, unchanged interface) ───────────────────────────


class GmailService:
    """Domain logic around OAuth, email fetching, and label application."""

    def __init__(self, adapter: GmailApiAdapter, settings: Settings) -> None:
        self._adapter = adapter
        self._settings = settings

    async def create_authorization_url(self, state: str, user_id: str) -> str:
        logger.debug("Generating Gmail OAuth URL for user %s", user_id)
        return self._adapter.get_authorization_url(state=state)

    async def exchange_code_for_tokens(self, code: str) -> GmailTokens:
        logger.debug("Exchanging authorization code for tokens")
        raw = self._adapter.exchange_code_for_tokens(code=code)
        token_data: dict = {
            "access_token": raw["access_token"],
            "refresh_token": raw["refresh_token"],
            "token_type": raw.get("token_type", "Bearer"),
        }
        if raw.get("expires_at"):
            token_data["expires_at"] = raw["expires_at"]
        if raw.get("scope"):
            token_data["scope"] = raw["scope"]
        return GmailTokens(**token_data)

    async def list_messages(
        self,
        tokens: GmailTokens,
        user_id: str,
        max_results: int = 20,
        query: str | None = None,
    ) -> list[dict]:
        return self._adapter.list_messages(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            max_results=max_results,
            query=query,
            user_id=user_id,
        )

    async def list_labels(self, tokens: GmailTokens, user_id: str) -> list[dict]:
        return self._adapter.list_labels(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )

    async def apply_label(
        self,
        message_id: str,
        label_id: str,
        tokens: GmailTokens,
        user_id: str,
    ) -> None:
        self._adapter.apply_label(
            message_id=message_id,
            label_name=label_id,
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )
