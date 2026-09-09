from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[3] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    max_pdf_pages: int = Field(default=50, ge=1, le=500)
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
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
    postgres_password: SecretStr = Field(min_length=1)
    postgres_host: str = "127.0.0.1"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @property
    def database_url(self) -> URL:
        # URL.create safely handles reserved characters in credentials.
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
