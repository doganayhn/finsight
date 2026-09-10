from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
import pytest
from conftest import TEST_AUTH_SECRET, auth_headers
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pdf_factory import synthetic_pdf
from pydantic import SecretStr, ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from test_imports import TEXT

from app.api.dependencies import get_auth_session
from app.core.config import Settings
from app.db.session import get_session
from app.main import create_app
from app.modules.accounts.models import Account
from app.modules.auth.models import AuthSession, User
from app.modules.auth.rate_limit import FixedWindowLimiter
from app.modules.auth.security import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    REFRESH_COOKIE_NAME,
    decode_access_token,
    issue_access_token,
    passwords,
)

PASSWORD = "correct horse battery staple"


@pytest.fixture
def auth_context(db_engine):
    settings = Settings(
        _env_file=None,
        app_env="test",
        postgres_password=SecretStr("synthetic-test-credential"),
        auth_jwt_secret=TEST_AUTH_SECRET,
        cors_origins=["http://localhost:5173"],
        auth_rate_limit_requests=100,
    )
    app = create_app(settings)

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_auth_session] = sessions
    try:
        with TestClient(app) as client:
            yield client, db_engine, settings, app
    finally:
        with db_engine.begin() as connection:
            connection.execute(delete(User).where(User.email.like("phase9-%@example.com")))


def email() -> str:
    return f"phase9-{uuid4().hex}@example.com"


def register(client, address=None, password=PASSWORD, **kwargs):
    return client.post(
        "/api/v1/auth/register",
        json={"email": address or email(), "password": password} | kwargs,
    )


def bearer(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def payload_for(user_id, session_id, *, now=None, **updates):
    now = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": now,
        "exp": now + timedelta(minutes=15),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
    }
    payload.update(updates)
    return payload


def test_registration_normalizes_email_creates_hash_session_and_cookie(auth_context):
    client, engine, _, _ = auth_context
    address = email()
    response = register(client, f"  {address.upper()}  ")
    assert response.status_code == 201
    assert response.json()["user"]["email"] == address
    assert set(response.json()) == {"access_token", "token_type", "user"}
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie
    assert "Path=/api/v1/auth" in cookie and "Secure" not in cookie
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.email == address))
        assert user and user.password_hash and PASSWORD not in user.password_hash
        assert user.password_hash.startswith("$argon2id$")
        assert passwords.verify(user.password_hash, PASSWORD)
        auth_session = session.scalar(select(AuthSession).where(AuthSession.user_id == user.id))
        assert auth_session and len(auth_session.refresh_token_hash) == 64
        assert response.cookies[REFRESH_COOKIE_NAME] not in auth_session.refresh_token_hash


def test_duplicate_registration_is_rejected_without_hash_disclosure(auth_context):
    client, *_ = auth_context
    address = email()
    assert register(client, address).status_code == 201
    response = register(client, address.upper())
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "registration_unavailable"}}
    assert "hash" not in response.text


@pytest.mark.parametrize("bad_password", ["short", "", "a" * 11])
def test_short_passwords_are_rejected(auth_context, bad_password):
    response = register(auth_context[0], password=bad_password)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}


def test_oversized_password_is_rejected_before_hashing(auth_context, monkeypatch):
    called = False

    def fail_if_called(value):
        nonlocal called
        called = True
        raise AssertionError("hash should not run")

    monkeypatch.setattr(passwords, "hash", fail_if_called)
    assert register(auth_context[0], password="x" * 129).status_code == 422
    assert called is False


@pytest.mark.parametrize("bad_email", ["missing-at", "a@", "@example.com", "a b@example.com"])
def test_invalid_email_is_rejected_safely(auth_context, bad_email):
    response = register(auth_context[0], bad_email)
    assert response.status_code == 422
    assert response.json() == {"detail": {"code": "invalid_request"}}


def test_login_succeeds_for_registered_credentials(auth_context):
    client, *_ = auth_context
    address = email()
    register(client, address)
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": address, "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["user"]["email"] == address
    assert response.cookies.get(REFRESH_COOKIE_NAME)


def test_login_failure_is_identical_for_unknown_email_and_wrong_password(auth_context):
    client, *_ = auth_context
    address = email()
    register(client, address)
    wrong = client.post(
        "/api/v1/auth/login", json={"email": address, "password": "incorrect password value"}
    )
    missing = client.post(
        "/api/v1/auth/login", json={"email": email(), "password": "incorrect password value"}
    )
    assert wrong.status_code == missing.status_code == 401
    assert wrong.json() == missing.json() == {"detail": {"code": "invalid_credentials"}}


def test_legacy_user_without_password_uses_generic_login_failure(auth_context):
    client, engine, *_ = auth_context
    address = email()
    with Session(engine) as session, session.begin():
        session.add(User(email=address))
    response = client.post("/api/v1/auth/login", json={"email": address, "password": PASSWORD})
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "invalid_credentials"}}


def test_access_jwt_has_only_minimal_expected_claims(auth_context):
    response = register(auth_context[0])
    raw = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    assert set(raw) == {"sub", "sid", "iat", "exp", "iss", "aud"}
    assert raw["iss"] == JWT_ISSUER and raw["aud"] == JWT_AUDIENCE
    assert raw["exp"] - raw["iat"] == 15 * 60


@pytest.mark.parametrize(
    "mutation",
    [
        {"iss": "wrong"},
        {"aud": "wrong"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
    ],
)
def test_invalid_standard_jwt_claims_are_rejected(auth_context, mutation):
    client, _, settings, _ = auth_context
    registered = register(client)
    claims = jwt.decode(registered.json()["access_token"], options={"verify_signature": False})
    claims.update(mutation)
    token = jwt.encode(claims, settings.auth_jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_invalid_signature_is_rejected(auth_context):
    client, *_ = auth_context
    response = register(client)
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    token = jwt.encode(claims, "different-signing-secret-that-is-long-enough", algorithm="HS256")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_unsupported_jwt_algorithms_are_rejected(auth_context, algorithm):
    client, _, settings, _ = auth_context
    response = register(client)
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    token = jwt.encode(claims, settings.auth_jwt_secret.get_secret_value(), algorithm=algorithm)
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_unsigned_jwt_is_rejected(auth_context):
    client, *_ = auth_context
    response = register(client)
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    token = jwt.encode(claims, key="", algorithm="none")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_session_mismatch_and_subject_override_are_rejected(auth_context):
    client, _, settings, _ = auth_context
    response = register(client)
    claims = decode_access_token(settings, response.json()["access_token"])
    mismatch = issue_access_token(settings, claims.user_id, uuid4())
    override = issue_access_token(settings, uuid4(), claims.session_id)
    for token in (mismatch, override):
        result = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert result.status_code == 401


def test_revoked_or_expired_server_session_rejects_valid_access_jwt(auth_context):
    client, engine, settings, _ = auth_context
    first = register(client)
    claims = decode_access_token(settings, first.json()["access_token"])
    with Session(engine) as session, session.begin():
        auth_session = session.get(AuthSession, claims.session_id)
        auth_session.revoked_at = datetime.now(UTC)
    assert client.get("/api/v1/auth/me", headers=bearer(first)).status_code == 401
    second = register(client)
    claims = decode_access_token(settings, second.json()["access_token"])
    with Session(engine) as session, session.begin():
        auth_session = session.get(AuthSession, claims.session_id)
        auth_session.refresh_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me", headers=bearer(second)).status_code == 401


def test_refresh_rotates_and_old_token_is_invalid(auth_context):
    client, *_ = auth_context
    register(client)
    old = client.cookies[REFRESH_COOKIE_NAME]
    first = client.post("/api/v1/auth/refresh")
    new = client.cookies[REFRESH_COOKIE_NAME]
    assert first.status_code == 200 and new != old
    client.cookies.set(REFRESH_COOKIE_NAME, old, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_expired_refresh_is_rejected(auth_context):
    client, engine, settings, _ = auth_context
    response = register(client)
    claims = decode_access_token(settings, response.json()["access_token"])
    with Session(engine) as session, session.begin():
        auth_session = session.get(AuthSession, claims.session_id)
        auth_session.refresh_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_missing_and_malformed_refresh_tokens_are_rejected(auth_context):
    client, *_ = auth_context
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401
    client.cookies.set(REFRESH_COOKIE_NAME, "not-a-refresh-token", path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_concurrent_refresh_allows_exactly_one_rotation(auth_context):
    client, _, _, app = auth_context
    register(client)
    cookie = client.cookies[REFRESH_COOKIE_NAME]

    def refresh_once():
        with TestClient(app) as worker:
            return worker.post(
                "/api/v1/auth/refresh",
                headers={"Cookie": f"{REFRESH_COOKIE_NAME}={cookie}"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _: refresh_once(), range(2)))
    assert sorted(statuses) == [200, 401]


def test_logout_revokes_session_clears_cookie_and_invalidates_access(auth_context):
    client, engine, settings, _ = auth_context
    response = register(client)
    claims = decode_access_token(settings, response.json()["access_token"])
    result = client.post("/api/v1/auth/logout", headers=bearer(response))
    assert result.status_code == 204
    assert "Max-Age=0" in result.headers["set-cookie"]
    with Session(engine) as session:
        assert session.get(AuthSession, claims.session_id).revoked_at is not None
    assert client.get("/api/v1/auth/me", headers=bearer(response)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_me_returns_only_safe_identity_fields(auth_context):
    response = register(auth_context[0])
    me = auth_context[0].get("/api/v1/auth/me", headers=bearer(response))
    assert me.status_code == 200
    assert set(me.json()) == {"id", "email", "created_at"}
    assert "hash" not in me.text and "session" not in me.text and PASSWORD not in me.text


@pytest.mark.parametrize(
    "path", ["accounts", "imports", "transactions", "analytics/summary", "assistant/status"]
)
def test_protected_products_require_bearer_authentication(auth_context, path):
    response = auth_context[0].get(f"/api/v1/{path}")
    assert response.status_code == 401
    assert response.json() == {"detail": {"code": "authentication_required"}}


def test_development_header_never_authenticates(context):
    response = context[0].get("/api/v1/accounts", headers={"X-Dev-User-ID": str(context[1])})
    assert response.status_code == 401


def test_account_creation_uses_authenticated_owner_and_rejects_user_id(context, db_engine):
    body = {
        "display_name": "Synthetic savings",
        "institution_code": "SYNTHETIC_PROVIDER",
        "account_type": "SAVINGS",
        "currency": "USD",
    }
    created = context[0].post("/api/v1/accounts", headers=auth_headers(context), json=body)
    assert created.status_code == 201
    account_id = UUID(created.json()["id"])
    with Session(db_engine) as session:
        assert session.get(Account, account_id).user_id == context[1]
    rejected = context[0].post(
        "/api/v1/accounts",
        headers=auth_headers(context),
        json=body | {"user_id": str(context[2])},
    )
    assert rejected.status_code == 422


@pytest.mark.parametrize(
    "change",
    [{"account_type": "CRYPTO"}, {"currency": "try"}, {"currency": "USDD"}, {"display_name": " "}],
)
def test_account_creation_validates_canonical_fields(context, change):
    body = {
        "display_name": "Synthetic",
        "institution_code": None,
        "account_type": "CASH",
        "currency": "TRY",
    }
    response = context[0].post(
        "/api/v1/accounts", headers=auth_headers(context), json=body | change
    )
    assert response.status_code == 422


def test_unauthenticated_account_creation_rejected_and_accounts_are_isolated(context):
    body = {"display_name": "Synthetic", "account_type": "CASH", "currency": "TRY"}
    assert context[0].post("/api/v1/accounts", json=body).status_code == 401
    created = context[0].post("/api/v1/accounts", headers=auth_headers(context), json=body)
    assert created.status_code == 201
    own = context[0].get("/api/v1/accounts", headers=auth_headers(context)).json()["accounts"]
    other = (
        context[0]
        .get("/api/v1/accounts", headers=auth_headers(context, context[2]))
        .json()["accounts"]
    )
    assert created.json()["id"] in {row["id"] for row in own}
    assert created.json()["id"] not in {row["id"] for row in other}


def test_newly_registered_user_starts_with_no_accounts(auth_context):
    response = register(auth_context[0])
    accounts = auth_context[0].get("/api/v1/accounts", headers=bearer(response))
    assert accounts.status_code == 200 and accounts.json()["accounts"] == []


def test_refresh_and_logout_reject_untrusted_origin(auth_context):
    client, *_ = auth_context
    response = register(client)
    assert (
        client.post("/api/v1/auth/refresh", headers={"Origin": "https://evil.example"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers=bearer(response) | {"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/auth/refresh", headers={"Origin": "http://localhost:5173"}).status_code
        == 200
    )


def test_credentialed_cors_is_explicit(auth_context):
    client, *_ = auth_context
    allowed = client.options(
        "/api/v1/auth/refresh",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    denied = client.options(
        "/api/v1/auth/refresh",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_production_cookie_is_secure(auth_context):
    _, engine, _, _ = auth_context
    settings = Settings(
        _env_file=None,
        app_env="production",
        postgres_password=SecretStr("synthetic"),
        auth_jwt_secret=SecretStr("Kf9!qZ2@vT7#nM4$xP8&cR6*eW3_yU1+"),
        cors_origins=["https://app.finsight.example"],
        auth_refresh_cookie_secure=True,
    )
    app = create_app(settings)

    def sessions():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        response = register(client)
    assert response.status_code == 201 and "Secure" in response.headers["set-cookie"]


@pytest.mark.parametrize(
    "updates",
    [
        {"auth_jwt_secret": SecretStr("short")},
        {"auth_jwt_secret": SecretStr("replace-with-production-secret-value-12345")},
        {"auth_refresh_cookie_secure": False},
        {"cors_origins": ["http://app.finsight.example"]},
        {"cors_origins": ["*"]},
    ],
)
def test_unsafe_production_configuration_fails_fast(updates):
    safe = {
        "_env_file": None,
        "app_env": "production",
        "postgres_password": SecretStr("synthetic"),
        "auth_jwt_secret": SecretStr("Kf9!qZ2@vT7#nM4$xP8&cR6*eW3_yU1+"),
        "cors_origins": ["https://app.finsight.example"],
        "auth_refresh_cookie_secure": True,
    }
    with pytest.raises(ValidationError):
        Settings(**(safe | updates))


def test_invalid_app_environment_and_missing_auth_secret_fail_fast():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            app_env="staging",
            postgres_password=SecretStr("synthetic"),
            auth_jwt_secret=TEST_AUTH_SECRET,
        )
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            postgres_password=SecretStr("synthetic"),
            auth_jwt_secret=None,
        )


def test_rate_limiter_enforces_window_expires_and_bounds_memory():
    limiter = FixedWindowLimiter(limit=2, window_seconds=10, max_keys=32)
    limiter.check("login:one", now=0)
    limiter.check("login:one", now=1)
    with pytest.raises(Exception, match="auth_rate_limited"):
        limiter.check("login:one", now=2)
    limiter.check("login:one", now=11)
    for index in range(50):
        limiter.check(f"register:{index}", now=11)
    assert limiter.key_count == 32
    limiter.check("fresh", now=22)
    assert limiter.key_count == 1


def test_auth_endpoint_rate_limit_uses_client_host(db_engine):
    settings = Settings(
        _env_file=None,
        app_env="test",
        postgres_password=SecretStr("synthetic"),
        auth_jwt_secret=TEST_AUTH_SECRET,
        cors_origins=["http://localhost:5173"],
        auth_rate_limit_requests=2,
    )
    app = create_app(settings)

    def sessions():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    with TestClient(app) as client:
        for _ in range(2):
            assert (
                client.post(
                    "/api/v1/auth/login", json={"email": email(), "password": PASSWORD}
                ).status_code
                == 401
            )
        limited = client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": str(uuid4())},
            json={"email": email(), "password": PASSWORD},
        )
        assert limited.status_code == 429


def test_auth_material_is_absent_from_request_logs(auth_context, caplog):
    caplog.set_level("INFO", logger="finsight.requests")
    response = register(auth_context[0])
    token = response.json()["access_token"]
    auth_context[0].get("/api/v1/auth/me", headers=bearer(response))
    rendered = caplog.text
    assert PASSWORD not in rendered and token not in rendered
    assert REFRESH_COOKIE_NAME not in rendered


def test_request_id_is_server_generated_and_security_headers_exist(auth_context):
    response = auth_context[0].get("/api/v1/health", headers={"X-Request-ID": "caller-controlled"})
    assert UUID(response.headers["x-request-id"])
    assert response.headers["x-request-id"] != "caller-controlled"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


def test_unexpected_errors_are_sanitized(auth_context):
    _, _, settings, app = auth_context
    probe = APIRouter()

    @probe.get("/synthetic-failure")
    def failure():
        raise RuntimeError("C:/private/path password=PRIVATE_SECRET SELECT * FROM users")

    app.include_router(probe, prefix="/api/v1")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/synthetic-failure")
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "internal_error"}}
    assert "PRIVATE_SECRET" not in response.text and "C:/private" not in response.text


def test_health_live_and_database_readiness(auth_context):
    client, *_ = auth_context
    assert client.get("/api/v1/health").json() == {"status": "ok"}
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    assert client.get("/api/v1/health/ready").json() == {"status": "ok"}


def test_disposable_authenticated_product_flow_and_second_user_isolation(auth_context):
    client, *_ = auth_context
    first_email = email()
    registered = register(client, first_email)
    first_headers = bearer(registered)
    assert client.get("/api/v1/auth/me", headers=first_headers).status_code == 200
    assert client.get("/api/v1/accounts", headers=first_headers).json()["accounts"] == []

    created = client.post(
        "/api/v1/accounts",
        headers=first_headers,
        json={
            "display_name": "Synthetic TLcard",
            "institution_code": "YAPI_KREDI",
            "account_type": "DEBIT_CARD",
            "currency": "TRY",
        },
    )
    assert created.status_code == 201
    account_id = created.json()["id"]
    preview = client.post(
        "/api/v1/imports/preview",
        headers=first_headers,
        data={"account_id": account_id},
        files={
            "file": (
                "synthetic.pdf",
                synthetic_pdf(TEXT.split("\f")),
                "application/pdf",
            )
        },
    )
    assert preview.status_code == 201
    batch_id = preview.json()["import_batch_id"]
    confirmed = client.post(
        f"/api/v1/imports/{batch_id}/confirm",
        headers=first_headers,
        json={"decisions": {}},
    )
    assert confirmed.status_code == 200 and confirmed.json()["counts"]["imported_rows"] == 3
    period = {"start_date": "2024-01-01", "end_date": "2024-01-31"}
    summary = client.get("/api/v1/analytics/summary", headers=first_headers, params=period)
    assert (
        summary.status_code == 200 and summary.json()["currencies"][0]["net_spending"] == "1340.00"
    )
    transactions = client.get("/api/v1/transactions", headers=first_headers, params=period)
    assert transactions.status_code == 200 and len(transactions.json()["transactions"]) == 3
    transaction_id = transactions.json()["transactions"][0]["id"]
    categories = client.get("/api/v1/categories", headers=first_headers).json()
    cafe = next(row for row in categories if row["code"] == "CAFE")
    corrected = client.patch(
        f"/api/v1/transactions/{transaction_id}/classification",
        headers=first_headers,
        json={"category_id": cafe["id"], "persist_as_rule": False},
    )
    assert corrected.status_code == 200
    assert client.get("/api/v1/assistant/status", headers=first_headers).status_code == 200

    assert client.post("/api/v1/auth/logout", headers=first_headers).status_code == 204
    assert client.get("/api/v1/accounts", headers=first_headers).status_code == 401
    logged_in = client.post("/api/v1/auth/login", json={"email": first_email, "password": PASSWORD})
    assert logged_in.status_code == 200
    first_headers = bearer(logged_in)
    assert account_id in {
        row["id"]
        for row in client.get("/api/v1/accounts", headers=first_headers).json()["accounts"]
    }

    second = register(client)
    second_headers = bearer(second)
    assert client.get("/api/v1/accounts", headers=second_headers).json()["accounts"] == []
    hidden = client.get(
        "/api/v1/analytics/summary",
        headers=second_headers,
        params=period | {"account_id": account_id},
    )
    assert hidden.status_code == 404 and hidden.json() == {"detail": {"code": "account_not_found"}}
