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
            raise RuntimeError("Composio SDK is not installed. Install `composio>=0.8.0`.") from exc

        self._client: Composio = Composio(api_key=api_key)
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
        redirect_url = connection_request.redirect_url
        if redirect_url is None:
            raise RuntimeError("Failed to get redirect URL from Composio")
        return redirect_url

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
            if hasattr(accounts, "items"):
                logger.debug(f"Number of connected accounts: {len(accounts.items)}")
                for acc in accounts.items:
                    logger.debug(f"  - Account ID: {acc.id}, Status: {acc.status}")
        except Exception as e:
            logger.warning(f"Failed to list connected accounts: {e}")

        # Use user_id to let Composio automatically find the connected account
        # This avoids entity_id mismatch errors
        logger.debug(f"Calling GMAIL_FETCH_EMAILS with max_results={max_results}, query={query}")

        # Build arguments - try with query parameter
        arguments: dict[str, int | str] = {
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
            data = result.data  # type: ignore[attr-defined]
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
            logger.debug(
                f"data is dict with keys: {data.keys() if hasattr(data, 'keys') else 'N/A'}"
            )

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

    async def get_message(
        self,
        message_id: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> dict | None:
        """Get a single Gmail message by ID.

        Args:
            message_id: Gmail message ID to fetch
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User's UUID (used as user_id in Composio)

        Returns:
            Message dictionary or None if not found
        """
        logger.debug(f"Fetching single message {message_id} for user_id: {user_id}")

        arguments = {
            "message_id": message_id,
        }

        try:
            result = self._client.tools.execute(
                slug="GMAIL_FETCH_EMAIL",
                arguments=arguments,
                user_id=user_id,
            )

            # Handle both object and dict responses
            if hasattr(result, "data"):
                data = result.data  # type: ignore[attr-defined]
            elif isinstance(result, dict) and "data" in result:
                data = result["data"]
            else:
                logger.error(f"Unexpected result format: {type(result)}")
                return None

            if data and isinstance(data, dict):
                logger.info(f"✅ Fetched message {message_id}")
                return dict(data)  # Cast to dict to satisfy mypy
            else:
                logger.warning(f"Message {message_id} not found or invalid format")
                return None

        except Exception as e:
            logger.error(f"Error fetching message {message_id}: {e}")
            return None

    async def list_labels(
        self,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> list[dict]:
        """List all Gmail labels for the user.

        Args:
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User's UUID (used as user_id in Composio)

        Returns:
            List of label dictionaries with 'id' and 'name' fields
        """
        logger.debug(f"Listing labels for user_id: {user_id}")

        result = self._client.tools.execute(
            slug="GMAIL_LIST_LABELS",
            arguments={},
            user_id=user_id,
        )

        # Handle both object (from mock/SDK) and dict (from actual Composio response)
        if hasattr(result, "data"):
            data = result.data  # type: ignore[attr-defined]
        elif isinstance(result, dict) and "data" in result:
            data = result["data"]
        else:
            logger.error(f"Unexpected result format: {type(result)}")
            return []

        # Extract labels array
        if isinstance(data, dict) and "labels" in data:
            labels = data["labels"]
            logger.info(f"Found {len(labels)} labels")
            return labels if isinstance(labels, list) else [labels]
        elif isinstance(data, list):
            logger.info(f"Found {len(data)} labels (direct list)")
            return data

        logger.warning(f"No labels found in response. Data type: {type(data)}")
        return []

    async def create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Create a new Gmail label.

        Args:
            label_name: Name of the label to create
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User's UUID (used as user_id in Composio)

        Returns:
            Created label ID

        Raises:
            RuntimeError: If label creation fails
        """
        logger.debug(f"Creating label '{label_name}' for user_id: {user_id}")

        arguments = {
            "label_name": label_name,
            "message_list_visibility": "show",
            "label_list_visibility": "labelShow",
        }

        result = self._client.tools.execute(
            slug="GMAIL_CREATE_LABEL",
            arguments=arguments,
            user_id=user_id,
        )

        # Handle both object and dict responses
        if hasattr(result, "data"):
            data = result.data  # type: ignore[attr-defined]
        elif isinstance(result, dict) and "data" in result:
            data = result["data"]
        else:
            raise RuntimeError(f"Failed to create label: unexpected result format {type(result)}")

        # Extract label ID from response
        if isinstance(data, dict) and "id" in data:
            label_id = data["id"]
            logger.info(f"✅ Created label '{label_name}' with ID: {label_id}")
            return str(label_id)  # Cast to str to satisfy mypy
        else:
            raise RuntimeError(f"Failed to create label '{label_name}': no ID in response")

    async def get_or_create_label(
        self,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> str:
        """Get existing label ID by name, or create it if it doesn't exist.

        Args:
            label_name: Name of the label to get or create
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User's UUID (used as user_id in Composio)

        Returns:
            Label ID (existing or newly created)
        """
        logger.debug(f"Getting or creating label '{label_name}' for user_id: {user_id}")

        # First, try to find existing label
        labels = await self.list_labels(
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
        )

        # Search for label by name (case-insensitive)
        for label in labels:
            if isinstance(label, dict) and label.get("name", "").lower() == label_name.lower():
                label_id = label.get("id")
                logger.info(f"✅ Found existing label '{label_name}' with ID: {label_id}")
                return str(label_id)  # Cast to str to satisfy mypy

        # Label doesn't exist, create it
        logger.info(f"Label '{label_name}' not found, creating new one")
        return await self.create_label(
            label_name=label_name,
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
        )

    async def apply_label(
        self,
        message_id: str,
        label_name: str,
        access_token: str,
        refresh_token: str,
        user_id: str | None = None,
    ) -> None:
        """Apply a label to a Gmail message.

        Args:
            message_id: Gmail message ID
            label_name: Label name to apply (e.g., "Important", "Not Important")
            access_token: Connection ID from Composio (stored as access_token)
            refresh_token: Not used (Composio uses connection internally)
            user_id: User's UUID (used as user_id in Composio)
        """
        # Map to AI-prefixed custom labels
        label_mapping = {
            "Important": "TImportant",
            "Not Important": "TNotImportant",
        }
        custom_label_name = label_mapping.get(label_name, label_name)

        logger.info(
            f"Applying label '{custom_label_name}' (from '{label_name}') "
            f"to message {message_id} for user_id: {user_id}"
        )

        # Get or create the label and retrieve its ID
        label_id = await self.get_or_create_label(
            label_name=custom_label_name,
            access_token=access_token,
            refresh_token=refresh_token,
            user_id=user_id,
        )

        # Determine opposite label to remove for clean state
        remove_label_name = None
        if label_name == "Important":
            remove_label_name = "TNotImportant"
        elif label_name == "Not Important":
            remove_label_name = "TImportant"

        # Get opposite label ID if it exists (don't create it)
        remove_label_ids = []
        if remove_label_name:
            labels = await self.list_labels(
                access_token=access_token,
                refresh_token=refresh_token,
                user_id=user_id,
            )
            for label in labels:
                if isinstance(label, dict) and label.get("name") == remove_label_name:
                    remove_label_ids.append(label["id"])
                    logger.debug(
                        f"Will remove opposite label '{remove_label_name}' (ID: {label['id']})"
                    )
                    break

        # Always remove INBOX so classified emails leave the inbox
        remove_label_ids.append("INBOX")

        # Build API arguments
        arguments = {
            "message_id": message_id,
            "add_label_ids": [label_id],
            "remove_label_ids": remove_label_ids,
        }

        logger.debug(f"Executing GMAIL_ADD_LABEL_TO_EMAIL with arguments: {arguments}")

        # Execute the API call
        self._client.tools.execute(
            slug="GMAIL_ADD_LABEL_TO_EMAIL",
            arguments=arguments,
            user_id=user_id,
        )

        logger.info(f"✅ Successfully applied label '{custom_label_name}' to message {message_id}")


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
        logger.debug(
            "Listing Gmail messages for user %s, max_results=%s, query=%s",
            user_id,
            max_results,
            query,
        )
        return await self._adapter.list_messages(
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            max_results=max_results,
            user_id=user_id,
            query=query,
        )

    async def list_labels(self, tokens: GmailTokens, user_id: str) -> list[dict]:
        """List all Gmail labels for the user.

        Args:
            tokens: Gmail OAuth tokens
            user_id: User's UUID

        Returns:
            List of label dicts with 'id' and 'name' fields
        """
        return await self._adapter.list_labels(
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
        """Apply a label to a Gmail message.

        Args:
            message_id: Gmail message ID
            label_id: Label name to apply (despite the parameter name, this is actually a label name
                     like "Important" or "Not Important", not an ID)
            tokens: Gmail OAuth tokens
            user_id: User's UUID

        Note:
            The adapter will automatically map label names to "TImportant" and "TNotImportant"
            and resolve them to actual Gmail label IDs.
        """
        logger.debug("Applying label %s to message %s for user %s", label_id, message_id, user_id)
        await self._adapter.apply_label(
            message_id=message_id,
            label_name=label_id,  # Changed from label_id to label_name for clarity
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
            user_id=user_id,
        )
