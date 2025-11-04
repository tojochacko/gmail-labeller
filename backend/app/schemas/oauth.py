"""OAuth-related Pydantic schemas."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, SecretStr


class OAuthStartRequest(BaseModel):
    """Request payload for kicking off Gmail OAuth."""

    user_id: UUID = Field(..., description="Internal user identifier.")
    email: EmailStr = Field(..., description="User email address for Supabase record.")


class OAuthStartResponse(BaseModel):
    """OAuth consent URL payload."""

    authorization_url: AnyHttpUrl
    state: str


class OAuthCallbackRequest(BaseModel):
    """Payload received from the Electron app after OAuth redirect."""

    user_id: UUID
    # Traditional OAuth2 flow parameters
    code: Optional[str] = None
    state: Optional[str] = None
    # Composio-managed OAuth flow parameters
    connected_account_id: Optional[str] = None
    status: Optional[str] = None


class OAuthCallbackResponse(BaseModel):
    """Status after processing the OAuth callback."""

    connected: bool
    expires_at: datetime


class OAuthStatusResponse(BaseModel):
    """Connection status payload."""

    connected: bool
    expires_at: Optional[datetime] = None


class GmailTokens(BaseModel):
    """Normalized Gmail token payload stored in Supabase."""

    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scope: Optional[str] = None
    token_type: str = "Bearer"
    id_token: Optional[SecretStr] = None
