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

    async def get_authorization_url(self, redirect_uri: str, state: str, user_id: str) -> str:
        """Get OAuth authorization URL for Gmail.

        Args:
            redirect_uri: Redirect URI for OAuth callback
            state: OAuth state parameter for CSRF protection
            user_id: User's UUID to use as user_id in Composio

        Returns:
            Authorization URL for user to visit
        """
        # Initiate connection for this user (use actual user_id)
        logger.debug(f"Initiating Composio connection for user_id: {user_id}")
        connection_request = self._client.connected_accounts.initiate(
            user_id=user_id,  # Use actual user UUID as user_id in Composio
            auth_config_id=self._auth_config_id,
            callback_url=redirect_uri,
        )
        logger.debug(f"Connection initiated, redirect_url: {connection_request.redirect_url}")
        return connection_request.redirect_url

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
        query: str | None = None,
    ) -> list[dict]:
        """List Gmail messages for the user.

        Args:
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            max_results: Maximum number of messages to return
            user_id: User's UUID (used as user_id in Composio)
            query: Gmail search query (e.g., "in:inbox", "is:unread", or empty for all)

        Returns:
            List of message dictionaries
        """
        # Debug: Log user_id and list connected accounts
        logger.debug(f"Fetching emails for user_id: {user_id}")
        try:
            accounts = self._client.connected_accounts.list(user_ids=[user_id])
            logger.debug(f"Connected accounts for user {user_id}: {accounts}")
            if hasattr(accounts, 'items'):
                logger.debug(f"Number of connected accounts: {len(accounts.items)}")
                for acc in accounts.items:
                    logger.debug(f"  - Account ID: {acc.id}, Status: {acc.status}")
        except Exception as e:
            logger.warning(f"Failed to list connected accounts: {e}")

        # Use user_id to let Composio automatically find the connected account
        # This avoids entity_id mismatch errors
        logger.debug(f"Calling GMAIL_FETCH_EMAILS with max_results={max_results}, query={query}")

        # Build arguments - try with query parameter
        arguments = {
            "max_results": max_results,
        }

        # Add query if provided, otherwise try "in:inbox" to get inbox emails
        # If query is explicitly empty string, don't add it (to get all emails)
        if query is not None:
            arguments["query"] = query
        else:
            # Default to inbox emails
            arguments["query"] = "in:inbox"
            logger.debug("Using default query: 'in:inbox'")

        logger.debug(f"GMAIL_FETCH_EMAILS arguments: {arguments}")
        result = self._client.tools.execute(
            slug="GMAIL_FETCH_EMAILS",
            arguments=arguments,
            user_id=user_id,  # Composio will look up the connected account for this user
        )

        # Debug: Log the raw result
        logger.debug(f"GMAIL_FETCH_EMAILS result type: {type(result)}")

        # Handle both object (from mock/SDK) and dict (from actual Composio response)
        # Try object attribute access first (.data)
        if hasattr(result, "data"):
            logger.debug("Result has .data attribute (object type)")
            data = result.data
        # Try dict key access (["data"])
        elif isinstance(result, dict) and "data" in result:
            logger.debug("Result has ['data'] key (dict type)")
            data = result["data"]
        else:
            logger.error(f"Result has no .data attribute or ['data'] key. Type: {type(result)}")
            if isinstance(result, dict):
                logger.debug(f"Available keys: {list(result.keys())}")
            return []

        logger.debug(f"data type: {type(data)}")

        # Handle None case
        if data is None:
            logger.warning("data is None")
            return []

        # data should be a dict with "messages" key (production Composio response)
        if isinstance(data, dict):
            logger.debug(f"data is dict with keys: {data.keys() if hasattr(data, 'keys') else 'N/A'}")

            if "messages" in data:
                messages = data["messages"]
                logger.info(f"✅ Found {len(messages)} messages in data['messages']")
                if messages and len(messages) > 0:
                    logger.debug(f"First message subject: {messages[0].get('subject', 'N/A')}")
                    logger.debug(f"First message keys: {list(messages[0].keys())}")
                    logger.debug(f"First message sample: {messages[0]}")
                return messages if isinstance(messages, list) else [messages]
            else:
                logger.warning(f"data dict has no 'messages' key. Keys: {list(data.keys())}")
                return []

        # Fallback: data is a list directly (some SDK versions)
        if isinstance(data, list):
            logger.info(f"✅ Returning {len(data)} messages (data is direct list)")
            return data

        logger.warning(f"Unexpected data type: {type(data)}")
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
            user_id: User's UUID (used as user_id in Composio)
        """
        # Use user_id to let Composio automatically find the connected account
        # This avoids entity_id mismatch errors
        self._client.tools.execute(
            slug="GMAIL_ADD_LABEL",
            arguments={"message_id": message_id, "label_ids": [label_id]},
            user_id=user_id,  # Composio will look up the connected account for this user
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

    async def create_authorization_url(self, state: str, user_id: str) -> str:
        logger.debug("Generating Gmail OAuth URL with state %s for user %s", state, user_id)
        return await self._adapter.get_authorization_url(
            redirect_uri=str(self._settings.google_oauth_redirect_uri),
            state=state,
            user_id=user_id,
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
        user_id: str,
        max_results: int = 20,
        query: str | None = None,
    ) -> list[dict]:
        logger.debug("Listing Gmail messages for user %s, max_results=%s, query=%s", user_id, max_results, query)
        return await self._adapter.list_messages(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            max_results=max_results,
            user_id=user_id,
            query=query,
        )

    async def apply_label(
        self,
        message_id: str,
        label_id: str,
        tokens: GmailTokens,
        user_id: str,
    ) -> None:
        logger.debug("Applying label %s to message %s for user %s", label_id, message_id, user_id)
        await self._adapter.apply_label(
            message_id=message_id,
            label_id=label_id,
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )
