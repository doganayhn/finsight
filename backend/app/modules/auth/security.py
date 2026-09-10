from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
from secrets import token_urlsafe
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import Settings
from app.modules.auth.errors import AuthProblem

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "finsight"
JWT_AUDIENCE = "finsight-api"
REFRESH_COOKIE_NAME = "finsight_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    issued_at: datetime
    expires_at: datetime


class Passwords:
    """One deliberately bounded Argon2id policy for all first-party credentials."""

    def __init__(self):
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        # Missing users take the same Argon2 verification path as users with credentials.
        self._dummy_hash = self._hasher.hash("synthetic-dummy-password-never-used")

    def hash(self, password: str) -> str:
        return self._hasher.hash(password)

    def verify(self, password_hash: str | None, password: str) -> bool:
        candidate = password_hash or self._dummy_hash
        try:
            verified = self._hasher.verify(candidate, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        return bool(verified and password_hash)

    def needs_rehash(self, password_hash: str) -> bool:
        return self._hasher.check_needs_rehash(password_hash)


passwords = Passwords()


def utc_now() -> datetime:
    return datetime.now(UTC)


def issue_access_token(
    settings: Settings, user_id: UUID, session_id: UUID, *, now: datetime | None = None
) -> str:
    issued = now or utc_now()
    expires = issued + timedelta(minutes=settings.auth_access_token_minutes)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iat": issued,
            "exp": expires,
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
        },
        settings.auth_jwt_secret.get_secret_value(),
        algorithm=JWT_ALGORITHM,
    )


def decode_access_token(settings: Settings, token: str) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            settings.auth_jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["sub", "sid", "iat", "exp", "iss", "aud"]},
        )
        issued = datetime.fromtimestamp(int(payload["iat"]), UTC)
        expires = datetime.fromtimestamp(int(payload["exp"]), UTC)
        return AccessClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            issued_at=issued,
            expires_at=expires,
        )
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError, OverflowError) as error:
        raise AuthProblem("authentication_required", 401) from error


def new_refresh_token(session_id: UUID) -> tuple[str, str]:
    secret = token_urlsafe(48)
    return f"{session_id}.{secret}", refresh_hash(secret)


def parse_refresh_token(token: str) -> tuple[UUID, str]:
    try:
        session_text, secret = token.split(".", 1)
        session_id = UUID(session_text)
    except (ValueError, AttributeError) as error:
        raise AuthProblem("invalid_refresh_session", 401) from error
    if not secret or len(secret) > 256:
        raise AuthProblem("invalid_refresh_session", 401)
    return session_id, secret


def refresh_hash(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


def refresh_matches(stored_hash: str, secret: str) -> bool:
    return compare_digest(stored_hash, refresh_hash(secret))
