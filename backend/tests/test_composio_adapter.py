"""Integration tests for Composio 1.0 Gmail adapter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.gmail_toolkit import ComposioGmailAdapter, GmailService
from backend.app.schemas.oauth import GmailTokens


class MockConnectionRequest:
    """Mock for Composio ConnectionRequest response."""

    def __init__(self, redirect_url: str):
        self.redirect_url = redirect_url


class MockToolExecutionResponse:
    """Mock for Composio ToolExecutionResponse."""

    def __init__(self, data: list | dict | None):
        self.data = data
        self.successful = True
        self.error = None


# Alias for backward compatibility
MockExecuteResult = MockToolExecutionResponse


@pytest.fixture
def mock_composio_client():
    """Create a mock Composio client."""
    with patch("composio.Composio") as mock_composio_class:
        mock_client = MagicMock()

        # Mock connected_accounts.initiate
        mock_client.connected_accounts.initiate.return_value = MockConnectionRequest(
            redirect_url="https://accounts.google.com/o/oauth2/v2/auth?client_id=test"
        )

        # Mock tools.execute for fetching emails
        mock_client.tools.execute.return_value = MockToolExecutionResponse(
            data=[
                {
                    "id": "msg-1",
                    "threadId": "thread-1",
                    "subject": "Test Email",
                    "snippet": "Test content",
                }
            ]
        )

        mock_composio_class.return_value = mock_client
        yield mock_client


@pytest.mark.asyncio
async def test_adapter_initialization(mock_composio_client):
    """Test that ComposioGmailAdapter initializes correctly with API key."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    assert adapter is not None
    assert adapter._auth_config_id == "auth-config-123"


@pytest.mark.asyncio
async def test_get_authorization_url(mock_composio_client):
    """Test OAuth authorization URL generation using Composio 1.0 API."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    auth_url = await adapter.get_authorization_url(
        redirect_uri="http://localhost:3000/callback",
        state="random-state-123",
        user_id="test-user-456",
    )

    # Verify the correct Composio API was called
    mock_composio_client.connected_accounts.initiate.assert_called_once_with(
        user_id="test-user-456",
        auth_config_id="auth-config-123",
        callback_url="http://localhost:3000/callback",
    )

    # Verify the returned URL
    assert auth_url.startswith("https://accounts.google.com")
    assert "client_id" in auth_url


@pytest.mark.asyncio
async def test_exchange_code_for_tokens(mock_composio_client):
    """Test token exchange (which is handled by Composio automatically)."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    tokens = await adapter.exchange_code_for_tokens(
        code="auth-code-123", redirect_uri="http://localhost:3000/callback"
    )

    # Verify placeholder tokens are returned (Composio manages real tokens)
    assert tokens["access_token"] == "composio_managed"
    assert tokens["refresh_token"] == "composio_managed"
    assert tokens["token_type"] == "Bearer"
    assert tokens["scope"] == "gmail.modify"


@pytest.mark.asyncio
async def test_list_messages(mock_composio_client):
    """Test fetching Gmail messages using Composio 1.0 API."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    messages = await adapter.list_messages(
        access_token="conn-id-123",
        refresh_token="not-used",
        max_results=10,
        user_id="user-456",
        query="in:inbox",
    )

    # Verify the correct Composio API was called (only user_id, no connected_account_id)
    mock_composio_client.tools.execute.assert_called_once_with(
        slug="GMAIL_FETCH_EMAILS",
        arguments={"max_results": 10, "query": "in:inbox"},
        user_id="user-456",
    )

    # Verify the response
    assert len(messages) == 1
    assert messages[0]["id"] == "msg-1"
    assert messages[0]["subject"] == "Test Email"


@pytest.mark.asyncio
async def test_list_messages_with_composio_managed_token(mock_composio_client):
    """Test fetching messages when using Composio-managed tokens."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    await adapter.list_messages(
        access_token="composio_managed",
        refresh_token="composio_managed",
        max_results=20,
        user_id="user-789",
        query=None,  # Test with None (will use default "in:inbox")
    )

    # Should use only user_id (Composio looks up the connected account automatically)
    # query=None should default to "in:inbox"
    mock_composio_client.tools.execute.assert_called_once_with(
        slug="GMAIL_FETCH_EMAILS",
        arguments={"max_results": 20, "query": "in:inbox"},
        user_id="user-789",
    )


@pytest.mark.asyncio
async def test_apply_label(mock_composio_client):
    """Test applying labels to Gmail messages - verifies label name resolution to IDs."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    # Reset mock to clear previous calls
    mock_composio_client.tools.execute.reset_mock()

    # Mock list_labels response - "TImportant" already exists
    mock_composio_client.tools.execute.side_effect = [
        # First call: list_labels (from get_or_create_label)
        MockExecuteResult(
            data={
                "labels": [
                    {"id": "label-ai-important-123", "name": "TImportant"},
                    {"id": "label-ai-not-important-456", "name": "TNotImportant"},
                    {"id": "label-inbox", "name": "INBOX"},
                ]
            }
        ),
        # Second call: list_labels (to find opposite label)
        MockExecuteResult(
            data={
                "labels": [
                    {"id": "label-ai-important-123", "name": "TImportant"},
                    {"id": "label-ai-not-important-456", "name": "TNotImportant"},
                    {"id": "label-inbox", "name": "INBOX"},
                ]
            }
        ),
        # Third call: apply_label (GMAIL_ADD_LABEL_TO_EMAIL)
        MockExecuteResult(data={"successful": True}),
    ]

    await adapter.apply_label(
        message_id="msg-123",
        label_name="Important",  # Changed from label_id to label_name
        access_token="conn-id-789",
        refresh_token="not-used",
        user_id="user-abc",
    )

    # Verify three API calls were made
    assert mock_composio_client.tools.execute.call_count == 3

    # First call: list labels to find existing "TImportant" label (from get_or_create_label)
    first_call = mock_composio_client.tools.execute.call_args_list[0]
    assert first_call[1]["slug"] == "GMAIL_LIST_LABELS"
    assert first_call[1]["user_id"] == "user-abc"

    # Second call: list labels to find opposite label
    second_call = mock_composio_client.tools.execute.call_args_list[1]
    assert second_call[1]["slug"] == "GMAIL_LIST_LABELS"
    assert second_call[1]["user_id"] == "user-abc"

    # Third call: add label with resolved ID
    third_call = mock_composio_client.tools.execute.call_args_list[2]
    assert third_call[1]["slug"] == "GMAIL_ADD_LABEL_TO_EMAIL"
    assert third_call[1]["arguments"]["message_id"] == "msg-123"
    assert third_call[1]["arguments"]["add_label_ids"] == ["label-ai-important-123"]
    # Should try to remove opposite label
    assert third_call[1]["arguments"]["remove_label_ids"] == ["label-ai-not-important-456", "INBOX"]
    assert third_call[1]["user_id"] == "user-abc"


@pytest.mark.asyncio
async def test_apply_label_creates_new_label(mock_composio_client):
    """Test that apply_label creates a new label if it doesn't exist."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    mock_composio_client.tools.execute.reset_mock()

    # Mock responses: label doesn't exist, then create it, then apply it
    mock_composio_client.tools.execute.side_effect = [
        # First call: list_labels - "TImportant" doesn't exist
        MockExecuteResult(data={"labels": [{"id": "label-inbox", "name": "INBOX"}]}),
        # Second call: create_label
        MockExecuteResult(data={"id": "label-new-important-789", "name": "TImportant"}),
        # Third call: list_labels again (for finding opposite label to remove)
        MockExecuteResult(
            data={
                "labels": [
                    {"id": "label-inbox", "name": "INBOX"},
                    {"id": "label-new-important-789", "name": "TImportant"},
                ]
            }
        ),
        # Fourth call: apply_label
        MockExecuteResult(data={"successful": True}),
    ]

    await adapter.apply_label(
        message_id="msg-456",
        label_name="Important",
        access_token="conn-id-789",
        refresh_token="not-used",
        user_id="user-xyz",
    )

    # Verify create label was called
    assert mock_composio_client.tools.execute.call_count == 4
    create_call = mock_composio_client.tools.execute.call_args_list[1]
    assert create_call[1]["slug"] == "GMAIL_CREATE_LABEL"
    assert create_call[1]["arguments"]["label_name"] == "TImportant"


@pytest.mark.asyncio
async def test_list_labels(mock_composio_client):
    """Test listing Gmail labels."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    mock_composio_client.tools.execute.reset_mock()
    mock_composio_client.tools.execute.return_value = MockExecuteResult(
        data={
            "labels": [
                {"id": "label-1", "name": "INBOX"},
                {"id": "label-2", "name": "TImportant"},
                {"id": "label-3", "name": "Custom Label"},
            ]
        }
    )

    labels = await adapter.list_labels(
        access_token="conn-id",
        refresh_token="not-used",
        user_id="user-123",
    )

    assert len(labels) == 3
    assert labels[0]["name"] == "INBOX"
    assert labels[1]["name"] == "TImportant"
    mock_composio_client.tools.execute.assert_called_once_with(
        slug="GMAIL_LIST_LABELS",
        arguments={},
        user_id="user-123",
    )


@pytest.mark.asyncio
async def test_create_label(mock_composio_client):
    """Test creating a new Gmail label."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    mock_composio_client.tools.execute.reset_mock()
    mock_composio_client.tools.execute.return_value = MockExecuteResult(
        data={"id": "label-new-123", "name": "TImportant"}
    )

    label_id = await adapter.create_label(
        label_name="TImportant",
        access_token="conn-id",
        refresh_token="not-used",
        user_id="user-456",
    )

    assert label_id == "label-new-123"
    mock_composio_client.tools.execute.assert_called_once_with(
        slug="GMAIL_CREATE_LABEL",
        arguments={
            "label_name": "TImportant",
            "message_list_visibility": "show",
            "label_list_visibility": "labelShow",
        },
        user_id="user-456",
    )


@pytest.mark.asyncio
async def test_get_or_create_label_existing(mock_composio_client):
    """Test get_or_create_label when label already exists."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    mock_composio_client.tools.execute.reset_mock()
    mock_composio_client.tools.execute.return_value = MockExecuteResult(
        data={
            "labels": [
                {"id": "label-existing-123", "name": "TImportant"},
                {"id": "label-inbox", "name": "INBOX"},
            ]
        }
    )

    label_id = await adapter.get_or_create_label(
        label_name="TImportant",
        access_token="conn-id",
        refresh_token="not-used",
        user_id="user-789",
    )

    # Should only call list_labels, not create
    assert label_id == "label-existing-123"
    assert mock_composio_client.tools.execute.call_count == 1
    mock_composio_client.tools.execute.assert_called_with(
        slug="GMAIL_LIST_LABELS",
        arguments={},
        user_id="user-789",
    )


@pytest.mark.asyncio
async def test_get_or_create_label_new(mock_composio_client):
    """Test get_or_create_label when label doesn't exist and needs to be created."""
    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    mock_composio_client.tools.execute.reset_mock()
    mock_composio_client.tools.execute.side_effect = [
        # First call: list_labels - label doesn't exist
        MockExecuteResult(data={"labels": [{"id": "label-inbox", "name": "INBOX"}]}),
        # Second call: create_label
        MockExecuteResult(data={"id": "label-new-456", "name": "TNotImportant"}),
    ]

    label_id = await adapter.get_or_create_label(
        label_name="TNotImportant",
        access_token="conn-id",
        refresh_token="not-used",
        user_id="user-101",
    )

    assert label_id == "label-new-456"
    assert mock_composio_client.tools.execute.call_count == 2

    # Verify create was called
    create_call = mock_composio_client.tools.execute.call_args_list[1]
    assert create_call[1]["slug"] == "GMAIL_CREATE_LABEL"
    assert create_call[1]["arguments"]["label_name"] == "TNotImportant"


@pytest.mark.asyncio
async def test_gmail_service_with_adapter(mock_composio_client):
    """Test that GmailService works correctly with the new adapter."""
    from backend.app.config import Settings

    settings = Settings.model_validate(
        {
            "SUPABASE_URL": "https://test.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "test-key",
            "SUPABASE_ANON_KEY": "test-anon",
            "FERNET_SECRET_KEY": "test-fernet-key-32-chars-long!!",
            "COMPOSIO_API_KEY": "test-composio-key",
            "COMPOSIO_ACCOUNT_ID": "auth-config-123",
            "GOOGLE_OAUTH_CLIENT_ID": "test-client-id",
            "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret",
            "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:3000/callback",
        }
    )

    adapter = ComposioGmailAdapter(
        api_key=settings.composio_api_key.get_secret_value(),
        auth_config_id=settings.composio_account_id,
    )

    gmail_service = GmailService(adapter=adapter, settings=settings)

    # Test create_authorization_url
    state = "test-state-789"
    user_id = "test-user-999"
    auth_url = await gmail_service.create_authorization_url(state=state, user_id=user_id)
    assert auth_url.startswith("https://accounts.google.com")

    # Test exchange_code_for_tokens
    tokens = await gmail_service.exchange_code_for_tokens(code="test-code")
    assert isinstance(tokens, GmailTokens)
    assert tokens.access_token.get_secret_value() == "composio_managed"

    # Test list_messages
    mock_composio_client.tools.execute.reset_mock()
    messages = await gmail_service.list_messages(tokens=tokens, user_id=user_id, max_results=15)
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_adapter_handles_empty_response(mock_composio_client):
    """Test that adapter handles empty responses gracefully."""
    # Mock empty response
    mock_composio_client.tools.execute.return_value = MockToolExecutionResponse(data=None)

    adapter = ComposioGmailAdapter(api_key="test-api-key", auth_config_id="auth-config-123")

    messages = await adapter.list_messages(
        access_token="conn-id",
        refresh_token="not-used",
        max_results=10,
        user_id="test-user",
        query="in:inbox",
    )

    assert messages == []


@pytest.mark.asyncio
async def test_adapter_error_handling():
    """Test that adapter handles initialization errors gracefully."""
    # Test that adapter works when Composio is available
    with patch("composio.Composio") as mock_composio:
        mock_client = MagicMock()
        mock_composio.return_value = mock_client

        adapter = ComposioGmailAdapter(api_key="test-key", auth_config_id="test-config")
        assert adapter is not None
        assert adapter._auth_config_id == "test-config"
