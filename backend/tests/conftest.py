import pytest
from db_support import isolated_database, run_migration
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

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


@pytest.fixture(scope="session")
def db_engine():
    with isolated_database() as engine:
        run_migration(engine, "upgrade", "head")
        yield engine


@pytest.fixture
def db(db_engine):
    # Each test rolls back its synthetic data, even when it checks a constraint failure.
    with db_engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()
