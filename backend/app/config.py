"""Application configuration and settings."""

from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings


class OAuthClient(BaseModel):
    client_id: str
    client_secret: SecretStr
    redirect_uri: AnyHttpUrl
    scope: str = Field(default="https://www.googleapis.com/auth/gmail.modify")


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    # Database
    database_url: str = Field(default="sqlite+aiosqlite:///./data/app.db", alias="DATABASE_URL")

    # Encryption
    fernet_secret_key: SecretStr = Field(..., alias="FERNET_SECRET_KEY")
    jwt_secret_key: SecretStr = Field(..., alias="JWT_SECRET_KEY")

    # Environment
    environment: str = Field(default="production", alias="ENVIRONMENT")

    # External runtimes (optional - uses mock mode if not provided)
    agent_runtime_base_url: Optional[AnyHttpUrl] = Field(
        default=None, alias="AGENT_RUNTIME_BASE_URL"
    )

    # Gmail OAuth
    google_oauth_client_id: str = Field(..., alias="GOOGLE_OAUTH_CLIENT_ID")
    google_oauth_client_secret: SecretStr = Field(..., alias="GOOGLE_OAUTH_CLIENT_SECRET")
    google_oauth_redirect_uri: AnyHttpUrl = Field(..., alias="GOOGLE_OAUTH_REDIRECT_URI")
    google_oauth_scope: str = Field(
        default="https://www.googleapis.com/auth/gmail.modify", alias="GOOGLE_OAUTH_SCOPE"
    )

    # Optional telemetry
    sentry_dsn: Optional[str] = Field(default=None, alias="SENTRY_DSN")

    # Ollama Local LLM Configuration
    ollama_enabled: bool = Field(default=False, alias="OLLAMA_ENABLED")
    ollama_host: str = Field(default="http://localhost:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="gemma3", alias="OLLAMA_MODEL")

    # OpenAI Configuration
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")

    class Config:
        env_file = "config/.env"
        case_sensitive = True
        extra = "ignore"

    @model_validator(mode="after")
    def validate_presidio_for_cloud_llm(self) -> "Settings":
        """Fail fast if a cloud LLM key is set but Presidio is not installed."""
        if self.openai_api_key:
            try:
                import presidio_analyzer  # noqa: F401
            except ImportError:
                raise ValueError(
                    "presidio-analyzer must be installed when OPENAI_API_KEY is set. "
                    "Run: uv add presidio-analyzer presidio-anonymizer "
                    "&& python -m spacy download en_core_web_lg"
                )
        return self

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
