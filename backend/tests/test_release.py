import json

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings


def base_settings(**updates):
    return Settings(
        _env_file=None,
        postgres_password=SecretStr("synthetic-database-password"),
        auth_jwt_secret=SecretStr("synthetic-auth-secret-for-tests-only-0123456789"),
        **updates,
    )


def test_v1_version_is_exposed_as_openapi_metadata_without_changing_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    document = client.get("/api/v1/openapi.json").json()
    assert document["info"]["version"] == "1.0.0"


def test_openapi_excludes_private_auth_and_internal_statement_fields(client):
    document = client.get("/api/v1/openapi.json").json()
    encoded = json.dumps(document).lower()
    for private_name in (
        "password_hash",
        "refresh_token_hash",
        "database_url_override",
        "groq_api_key",
        "raw_pdf",
        "pdf_text",
        "provider_payload",
    ):
        assert private_name not in encoded
    assert "user_id" not in document["components"]["schemas"]["AccountCreate"]["properties"]


def test_database_url_is_a_validated_alternative_to_split_credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://synthetic:credential@db:5432/finsight")
    settings = Settings(
        _env_file=None,
        auth_jwt_secret=SecretStr("synthetic-auth-secret-for-tests-only-0123456789"),
    )
    assert settings.database_url.drivername == "postgresql+psycopg"
    assert settings.database_url.host == "db"
    assert settings.database_url.database == "finsight"


@pytest.mark.parametrize(
    "database_url",
    ["not-a-url", "postgresql://user:password@db/finsight", "sqlite:///local.db"],
)
def test_invalid_database_url_fails_fast(monkeypatch, database_url):
    monkeypatch.setenv("DATABASE_URL", database_url)
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(
            _env_file=None,
            auth_jwt_secret=SecretStr("synthetic-auth-secret-for-tests-only-0123456789"),
        )


def test_split_database_configuration_still_requires_a_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD or DATABASE_URL"):
        Settings(
            _env_file=None,
            auth_jwt_secret=SecretStr("synthetic-auth-secret-for-tests-only-0123456789"),
        )


def test_frontend_origins_environment_name_is_supported(monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGINS", '["https://app.example.invalid"]')
    assert base_settings().cors_origins == ["https://app.example.invalid"]
