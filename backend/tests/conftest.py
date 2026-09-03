import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr("test-only-not-a-real-credential"),
        postgres_host="database-not-required.invalid",
        cors_origins=["http://localhost:5173"],
    )
    with TestClient(create_app(settings)) as test_client:
        yield test_client
