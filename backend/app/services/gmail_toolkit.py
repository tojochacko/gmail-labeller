"""Adapter layer around the Composio Gmail toolkit."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)


class ComposioGmailAdapter:
    """Adapter that wraps Composio SDK for Gmail operations using Composio 1.0 API."""

    def __init__(self, api_key: str, auth_config_id: str) -> None:
        """Initialize the Composio Gmail adapter.

        Args:
            api_key: Composio API key
            auth_config_id: Auth config ID for Gmail OAuth configuration
        """
        try:
            from composio import Composio
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Composio SDK is not installed. Install `composio>=0.8.0`."
            ) from exc

        self._client = Composio(api_key=api_key)
        self._auth_config_id = auth_config_id

    async def get_authorization_url(self, redirect_uri: str, state: str) -> str:
        """Get OAuth authorization URL for Gmail.

        Args:
            redirect_uri: Redirect URI for OAuth callback
            state: OAuth state parameter for CSRF protection (stored in user_id)

        Returns:
            Authorization URL for user to visit
        """
        # Initiate connection for this user (using state as temporary user_id)
        connection_request = self._client.connected_accounts.initiate(
            user_id=state,  # Use state as user identifier during OAuth flow
            auth_config_id=self._auth_config_id,
            callback_url=redirect_uri,
        )
        return connection_request.redirectUrl

    async def exchange_code_for_tokens(self, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for access tokens.

        Note: With Composio 1.0, the token exchange happens automatically when the
        user completes OAuth. This method waits for the connection to be established.

        Args:
            code: Authorization code (used as user_id in Composio)
            redirect_uri: Redirect URI (not used with Composio's managed auth)

        Returns:
            Dictionary with token information
        """
        # In Composio 1.0, we don't need to manually exchange codes
        # The connection is established automatically via the OAuth callback
        # We just return a placeholder that indicates success
        return {
            "access_token": "composio_managed",
            "refresh_token": "composio_managed",
            # expires_at omitted - will use default from GmailTokens model
            "scope": "gmail.modify",
            "token_type": "Bearer",
            # id_token omitted - optional field
        }

    async def list_messages(
        self,
        access_token: str,
        refresh_token: str,
        max_results: int = 20,
        user_id: str | None = None,
    ) -> list[dict]:
        """List Gmail messages for the user.

        Args:
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            max_results: Maximum number of messages to return
            user_id: User ID to identify which connection to use (uses access_token if not provided)

        Returns:
            List of message dictionaries
        """
        # Use access_token as connected_account_id if user_id not provided
        connected_account_id = access_token if access_token != "composio_managed" else None

        result = self._client.tools.execute(
            slug="GMAIL_FETCH_EMAILS",
            arguments={"max_results": max_results},
            connected_account_id=connected_account_id,
            user_id=user_id,
        )

        # Parse and return messages
        if hasattr(result, "data") and result.data:
            return result.data if isinstance(result.data, list) else [result.data]
        return []

    async def apply_label(
        self,
        message_id: str,
        label_id: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> None:
        """Apply a label to a Gmail message.

        Args:
            message_id: Gmail message ID
            label_id: Gmail label ID to apply
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User ID to identify which connection to use (uses access_token if not provided)
        """
        # Use access_token as connected_account_id if user_id not provided
        connected_account_id = access_token if access_token != "composio_managed" else None

        self._client.tools.execute(
            slug="GMAIL_ADD_LABEL",
            arguments={"message_id": message_id, "label_ids": [label_id]},
            connected_account_id=connected_account_id,
            user_id=user_id,
        )


@dataclass
class GmailToolkitFactory:
    """Factory responsible for instantiating the Composio Gmail adapter."""

    settings: Settings

    def build(self) -> ComposioGmailAdapter:
        """Build and return a Composio Gmail adapter instance.

        Returns:
            Configured ComposioGmailAdapter instance
        """
        api_key = self.settings.composio_api_key.get_secret_value()
        # In Composio 1.0, composio_account_id is now the auth_config_id
        auth_config_id = self.settings.composio_account_id

        return ComposioGmailAdapter(api_key=api_key, auth_config_id=auth_config_id)


class GmailService:
    """Domain logic around OAuth, email fetching, and label application."""

    def __init__(
        self,
        adapter: ComposioGmailAdapter,
        settings: Settings,
    ) -> None:
        self._adapter = adapter
        self._settings = settings

    async def create_authorization_url(self, state: str) -> str:
        logger.debug("Generating Gmail OAuth URL with state %s", state)
        return await self._adapter.get_authorization_url(
            redirect_uri=str(self._settings.google_oauth_redirect_uri),
            state=state,
        )

    async def exchange_code_for_tokens(self, code: str) -> GmailTokens:
        logger.debug("Exchanging authorization code for tokens")
        raw_tokens = await self._adapter.exchange_code_for_tokens(
            code=code,
            redirect_uri=str(self._settings.google_oauth_redirect_uri),
        )
        # Build token dict, only including fields that are present
        token_data = {
            "access_token": raw_tokens["access_token"],
            "refresh_token": raw_tokens["refresh_token"],
            "token_type": raw_tokens.get("token_type", "Bearer"),
        }
        # Add optional fields only if present
        if "expires_at" in raw_tokens and raw_tokens["expires_at"] is not None:
            token_data["expires_at"] = raw_tokens["expires_at"]
        if "scope" in raw_tokens and raw_tokens["scope"] is not None:
            token_data["scope"] = raw_tokens["scope"]
        if "id_token" in raw_tokens and raw_tokens["id_token"] is not None:
            token_data["id_token"] = raw_tokens["id_token"]

        return GmailTokens(**token_data)

    async def list_messages(
        self,
        tokens: GmailTokens,
        max_results: int = 20,
    ) -> list[dict]:
        logger.debug("Listing Gmail messages for max_results=%s", max_results)
        return await self._adapter.list_messages(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            max_results=max_results,
        )

    async def apply_label(
        self,
        message_id: str,
        label_id: str,
        tokens: GmailTokens,
    ) -> None:
        logger.debug("Applying label %s to message %s", label_id, message_id)
        await self._adapter.apply_label(
            message_id=message_id,
            label_id=label_id,
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
        )
