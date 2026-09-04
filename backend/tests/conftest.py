from uuid import uuid4

import pytest
from db_support import isolated_database, run_migration
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from app.modules.accounts.enums import AccountType
from app.modules.accounts.models import Account
from app.modules.auth.models import User


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


@pytest.fixture
def account(db):
    user = User(email=f"synthetic-{uuid4().hex}@example.invalid")
    db.add(user)
    db.flush()
    account = Account(
        user_id=user.id,
        institution_code="SYNTHETIC_PROVIDER",
        display_name="Test card",
        account_type=AccountType.DEBIT_CARD,
        currency="TRY",
        account_number_masked="****1234",
    )
    db.add(account)
    db.flush()
    return account


@pytest.fixture
def context(db_engine):
    user_id, other_id, account_id = uuid4(), uuid4(), uuid4()
    with Session(db_engine) as session, session.begin():
        session.add_all(
            [User(id=uid, email=f"synthetic-{uid}@example.invalid") for uid in [user_id, other_id]]
        )
        session.flush()
        session.add(
            Account(
                id=account_id,
                user_id=user_id,
                display_name="Synthetic test account",
                account_type="DEBIT_CARD",
                currency="TRY",
            )
        )
    settings = get_settings().model_copy(update={"app_env": "development"})
    app = create_app(settings)

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            yield client, user_id, other_id, account_id, settings
    finally:
        with db_engine.begin() as connection:
            connection.execute(delete(User).where(User.id.in_([user_id, other_id])))
