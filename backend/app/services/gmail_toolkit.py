"""Adapter layer around the Composio Gmail toolkit."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..config import Settings
from ..schemas.oauth import GmailTokens


logger = logging.getLogger(__name__)


@runtime_checkable
class GmailToolkitProtocol(Protocol):
    """Subset of Composio Gmail toolkit methods the backend relies on."""

    async def get_authorization_url(self, redirect_uri: str, state: str) -> str: ...

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: str
    ) -> dict: ...

    async def list_messages(
        self, access_token: str, refresh_token: str, max_results: int = 20
    ) -> list[dict]: ...

    async def apply_label(
        self, message_id: str, label_id: str, access_token: str, refresh_token: str
    ) -> None: ...


@dataclass
class GmailToolkitFactory:
    """Factory responsible for instantiating the Composio Gmail toolkit."""

    settings: Settings

    def build(self) -> GmailToolkitProtocol:
        toolkit = self._create_toolkit()
        if not isinstance(toolkit, GmailToolkitProtocol):
            raise TypeError("Composio Gmail toolkit does not implement required protocol.")
        return toolkit

    def _create_toolkit(self) -> GmailToolkitProtocol:
        try:
            from composio import Composio
        except ImportError as exc:  # pragma: no cover - executed only if dependency missing
            raise RuntimeError(
                "Composio SDK is not installed. Install `composio>=0.8.0`."
            ) from exc

        api_key = self.settings.composio_api_key.get_secret_value()
        account_id = self.settings.composio_account_id
        client = Composio(api_key=api_key)
        try:
            toolkit = client.get_toolkit("gmail", account_id=account_id)
        except AttributeError as exc:  # pragma: no cover - safety guard
            raise RuntimeError(
                "Installed Composio SDK does not expose `get_toolkit`. "
                "Update to the latest release to use the Gmail toolkit."
            ) from exc
        return toolkit  # type: ignore[return-value]


class GmailService:
    """Domain logic around OAuth, email fetching, and label application."""

    def __init__(
        self,
        toolkit: GmailToolkitProtocol,
        settings: Settings,
    ) -> None:
        self._toolkit = toolkit
        self._settings = settings

    async def create_authorization_url(self, state: str) -> str:
        logger.debug("Generating Gmail OAuth URL with state {}", state)
        return await self._toolkit.get_authorization_url(
            redirect_uri=str(self._settings.google_oauth_redirect_uri),
            state=state,
        )

    async def exchange_code_for_tokens(self, code: str) -> GmailTokens:
        logger.debug("Exchanging authorization code for tokens")
        raw_tokens = await self._toolkit.exchange_code_for_tokens(
            code=code,
            redirect_uri=str(self._settings.google_oauth_redirect_uri),
        )
        return GmailTokens(
            access_token=raw_tokens["access_token"],
            refresh_token=raw_tokens["refresh_token"],
            expires_at=raw_tokens.get("expires_at"),
            scope=raw_tokens.get("scope"),
            token_type=raw_tokens.get("token_type", "Bearer"),
            id_token=raw_tokens.get("id_token"),
        )

    async def list_messages(
        self,
        tokens: GmailTokens,
        max_results: int = 20,
    ) -> list[dict]:
        logger.debug("Listing Gmail messages for max_results={}", max_results)
        return await self._toolkit.list_messages(
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
        logger.debug("Applying label {} to message {}", label_id, message_id)
        await self._toolkit.apply_label(
            message_id=message_id,
            label_id=label_id,
            access_token=tokens.access_token.get_secret_value(),
            refresh_token=tokens.refresh_token.get_secret_value(),
        )
