from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: Literal["development", "test", "production"] = "development"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_pdf_pages: int = Field(default=50, ge=1, le=500)
    groq_api_key: SecretStr | None = None
    groq_model: str = "openai/gpt-oss-120b"
    assistant_max_message_chars: int = Field(default=4000, ge=100, le=20000)
    assistant_max_history_messages: int = Field(default=10, ge=0, le=20)
    assistant_max_history_chars: int = Field(default=12000, ge=0, le=50000)
    assistant_max_tool_rounds: int = Field(default=4, ge=1, le=8)
    assistant_max_tool_calls: int = Field(default=8, ge=1, le=16)
    assistant_max_provider_calls: int = Field(default=6, ge=1, le=10)
    assistant_provider_timeout_seconds: float = Field(default=20, gt=0, le=60)
    assistant_max_output_tokens: int = Field(default=700, ge=100, le=2000)
    postgres_db: str = "finsight"
    postgres_user: str = "finsight"
    postgres_password: SecretStr | None = Field(default=None, min_length=1)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    database_url_override: SecretStr | None = Field(
        default=None, validation_alias="DATABASE_URL", exclude=True
    )
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://127.0.0.1:5173"],
        validation_alias=AliasChoices("FRONTEND_ORIGINS", "CORS_ORIGINS"),
    )
    auth_jwt_secret: SecretStr = Field(min_length=32)
    auth_access_token_minutes: int = Field(default=15, ge=5, le=60)
    auth_refresh_token_days: int = Field(default=30, ge=1, le=90)
    auth_refresh_cookie_secure: bool = False
    auth_rate_limit_requests: int = Field(default=10, ge=1, le=100)
    auth_rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    auth_rate_limit_max_keys: int = Field(default=2048, ge=32, le=100000)

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in origins:
            origin = raw.strip().rstrip("/")
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain explicit HTTP(S) origins")
            if origin not in normalized:
                normalized.append(origin)
        if not normalized:
            raise ValueError("CORS_ORIGINS must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_production_auth(self):
        if self.database_url_override is not None:
            try:
                url = make_url(self.database_url_override.get_secret_value())
            except ArgumentError as error:
                raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from error
            if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
                raise ValueError(
                    "DATABASE_URL must use postgresql+psycopg and include a host and database"
                )
        elif self.postgres_password is None:
            raise ValueError("POSTGRES_PASSWORD or DATABASE_URL is required")
        if self.app_env != "production":
            return self
        secret = self.auth_jwt_secret.get_secret_value()
        unsafe_markers = ("change", "replace", "placeholder", "development", "example")
        if (
            len(secret) < 32
            or len(set(secret)) < 12
            or any(marker in secret.lower() for marker in unsafe_markers)
        ):
            raise ValueError("Production AUTH_JWT_SECRET must be a strong non-placeholder secret")
        if not self.auth_refresh_cookie_secure:
            raise ValueError("Production refresh cookies must be Secure")
        if any(not origin.startswith("https://") for origin in self.cors_origins):
            raise ValueError("Production CORS_ORIGINS must use HTTPS")
        return self

    @property
    def database_url(self) -> URL:
        if self.database_url_override is not None:
            return make_url(self.database_url_override.get_secret_value())
        # URL.create safely handles reserved characters in credentials.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value() if self.postgres_password else None,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
