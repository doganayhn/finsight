from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from db_support import isolated_database, run_migration
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.dependencies import get_auth_session
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app
from app.modules.accounts.enums import AccountType
from app.modules.accounts.models import Account
from app.modules.auth.models import AuthSession, User
from app.modules.auth.security import issue_access_token

TEST_AUTH_SECRET = SecretStr("p9_T3st!Only_Kf7@Secure_NeverProduction_0123456789_ABCDEFGHIJKLMN")


def auth_headers(context, user_id=None):
    return context[0]._auth_headers[user_id or context[1]]


@pytest.fixture
def client():
    settings = Settings(
        _env_file=None,
        postgres_password=SecretStr("test-only-not-a-real-credential"),
        auth_jwt_secret=TEST_AUTH_SECRET,
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
    settings = get_settings().model_copy(
        update={"app_env": "test", "auth_jwt_secret": TEST_AUTH_SECRET}
    )
    session_ids = {user_id: uuid4(), other_id: uuid4()}
    with Session(db_engine) as session, session.begin():
        session.add_all(
            [User(id=uid, email=f"synthetic-{uid}@example.invalid") for uid in [user_id, other_id]]
        )
        session.flush()
        session.add_all(
            AuthSession(
                id=session_ids[uid],
                user_id=uid,
                refresh_token_hash="0" * 64,
                refresh_expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            for uid in (user_id, other_id)
        )
        session.add(
            Account(
                id=account_id,
                user_id=user_id,
                display_name="Synthetic test account",
                account_type="DEBIT_CARD",
                currency="TRY",
            )
        )
    app = create_app(settings)

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_auth_session] = sessions
    try:
        with TestClient(app) as client:
            client._auth_headers = {
                uid: {
                    "Authorization": f"Bearer {issue_access_token(settings, uid, session_ids[uid])}"
                }
                for uid in (user_id, other_id)
            }
            yield client, user_id, other_id, account_id, settings
    finally:
        with db_engine.begin() as connection:
            connection.execute(delete(User).where(User.id.in_([user_id, other_id])))
