"""Tests for GmailApiAdapter (direct Gmail API)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.services.gmail_toolkit import GmailApiAdapter


ADAPTER_KWARGS = dict(
    client_id="test-client-id",
    client_secret="test-secret",
    redirect_uri="http://localhost:8000/oauth/callback",
    scopes=["https://www.googleapis.com/auth/gmail.modify"],
)


@pytest.fixture
def adapter() -> GmailApiAdapter:
    return GmailApiAdapter(**ADAPTER_KWARGS)


class TestGetAuthorizationUrl:
    def test_returns_google_url(self, adapter: GmailApiAdapter) -> None:
        url = adapter.get_authorization_url(state="abc123")
        assert "accounts.google.com" in url
        assert "abc123" in url

    def test_includes_offline_access(self, adapter: GmailApiAdapter) -> None:
        url = adapter.get_authorization_url(state="xyz")
        assert "offline" in url or "access_type=offline" in url


class TestExchangeCodeForTokens:
    def test_returns_token_dict(self, adapter: GmailApiAdapter) -> None:
        mock_creds = MagicMock()
        mock_creds.token = "access-token-123"
        mock_creds.refresh_token = "refresh-token-456"
        mock_creds.expiry = None
        mock_creds.scopes = {"https://www.googleapis.com/auth/gmail.modify"}

        mock_flow = MagicMock()
        mock_flow.credentials = mock_creds

        with patch("backend.app.services.gmail_toolkit.Flow") as mock_flow_cls:
            mock_flow_cls.from_client_config.return_value = mock_flow
            result = adapter.exchange_code_for_tokens(code="auth-code")

        assert result["access_token"] == "access-token-123"
        assert result["refresh_token"] == "refresh-token-456"
        assert result["token_type"] == "Bearer"
        mock_flow.fetch_token.assert_called_once_with(code="auth-code")


class TestListMessages:
    @pytest.fixture
    def mock_service(self) -> MagicMock:
        msg_list = MagicMock()
        msg_list.execute.return_value = {
            "messages": [{"id": "msg1", "threadId": "t1"}]
        }
        msg_get = MagicMock()
        msg_get.execute.return_value = {
            "id": "msg1",
            "threadId": "t1",
            "snippet": "Hello world",
            "payload": {
                "headers": [
                    {"name": "Subject", "value": "Test Subject"},
                    {"name": "From", "value": "sender@example.com"},
                    {"name": "Date", "value": "Mon, 27 Mar 2026 10:00:00 +0000"},
                ]
            },
            "labelIds": ["INBOX"],
        }
        svc = MagicMock()
        svc.users.return_value.messages.return_value.list.return_value = msg_list
        svc.users.return_value.messages.return_value.get.return_value = msg_get
        return svc

    def test_returns_message_list(self, adapter: GmailApiAdapter, mock_service: MagicMock) -> None:
        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_service):
            result = adapter.list_messages(
                access_token="tok",
                refresh_token="ref",
                max_results=10,
                query="in:inbox",
            )

        assert len(result) == 1
        assert result[0]["id"] == "msg1"
        assert result[0]["snippet"] == "Hello world"

    def test_returns_empty_on_no_messages(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.messages.return_value.list.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_messages(
                access_token="tok", refresh_token="ref", max_results=10
            )

        assert result == []


class TestListLabels:
    def test_returns_labels(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [{"id": "Label_1", "name": "TImportant"}]
        }

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_labels(access_token="tok", refresh_token="ref")

        assert len(result) == 1
        assert result[0]["name"] == "TImportant"

    def test_returns_empty_when_no_labels(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            result = adapter.list_labels(access_token="tok", refresh_token="ref")

        assert result == []


class TestCreateLabel:
    def test_returns_label_id(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.create.return_value.execute.return_value = {
            "id": "Label_42",
            "name": "TImportant",
        }

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            label_id = adapter.create_label(
                label_name="TImportant", access_token="tok", refresh_token="ref"
            )

        assert label_id == "Label_42"

    def test_raises_on_missing_id(self, adapter: GmailApiAdapter) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.create.return_value.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            with pytest.raises(RuntimeError, match="no ID in response"):
                adapter.create_label(
                    label_name="Bad", access_token="tok", refresh_token="ref"
                )


class TestApplyLabel:
    def test_applies_important_label_and_removes_inbox(
        self, adapter: GmailApiAdapter
    ) -> None:
        mock_svc = MagicMock()
        mock_svc.users.return_value.labels.return_value.list.return_value.execute.return_value = {
            "labels": [
                {"id": "Label_1", "name": "TImportant"},
                {"id": "Label_2", "name": "TNotImportant"},
            ]
        }
        modify_call = mock_svc.users.return_value.messages.return_value.modify.return_value
        modify_call.execute.return_value = {}

        with patch("backend.app.services.gmail_toolkit.build", return_value=mock_svc):
            adapter.apply_label(
                message_id="msg1",
                label_name="Important",
                access_token="tok",
                refresh_token="ref",
            )

        modify_call.execute.assert_called_once()
        call_body = mock_svc.users.return_value.messages.return_value.modify.call_args[1]["body"]
        assert "Label_1" in call_body["addLabelIds"]
        assert "Label_2" in call_body["removeLabelIds"]
        assert "INBOX" in call_body["removeLabelIds"]
