"""Application configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings


class OAuthClient(BaseModel):
    client_id: str
    client_secret: SecretStr
    redirect_uri: AnyHttpUrl
    scope: str = Field(default="https://www.googleapis.com/auth/gmail.modify")


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    # Supabase
    supabase_url: AnyHttpUrl = Field(..., alias="SUPABASE_URL")
    supabase_service_role_key: SecretStr = Field(..., alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_anon_key: SecretStr = Field(..., alias="SUPABASE_ANON_KEY")

    # Encryption
    fernet_secret_key: SecretStr = Field(..., alias="FERNET_SECRET_KEY")

    # External runtimes (optional - uses mock mode if not provided)
    agent_runtime_base_url: Optional[AnyHttpUrl] = Field(
        default=None, alias="AGENT_RUNTIME_BASE_URL"
    )

    # Composio
    composio_api_key: SecretStr = Field(..., alias="COMPOSIO_API_KEY")
    composio_account_id: str = Field(..., alias="COMPOSIO_ACCOUNT_ID")

    # Gmail OAuth
    google_oauth_client_id: str = Field(..., alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: SecretStr = Field(..., alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: AnyHttpUrl = Field(..., alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_oauth_scope: str = Field(
        default="https://www.googleapis.com/auth/gmail.modify", alias="GOOGLE_OAUTH_SCOPE"
    )

    # Optional telemetry
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")

    class Config:
        env_file = "config/.env"
        case_sensitive = True
        extra = "ignore"

    @property
    def oauth_client(self) -> OAuthClient:
        return OAuthClient(
            client_id=self.google_oauth_client_id,
            client_secret=self.google_oauth_client_secret,
            redirect_uri=self.google_oauth_redirect_uri,
            scope=self.google_oauth_scope,
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()  # type: ignore[call-arg]
