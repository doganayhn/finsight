from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.errors import AuthProblem
from app.modules.auth.models import AuthSession, User
from app.modules.auth.schemas import CredentialsRequest
from app.modules.auth.security import (
    issue_access_token,
    new_refresh_token,
    parse_refresh_token,
    passwords,
    refresh_matches,
    utc_now,
)


@dataclass(frozen=True)
class AuthResult:
    user: User
    access_token: str
    refresh_token: str


class AuthService:
    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings

    def register(self, credentials: CredentialsRequest) -> AuthResult:
        if self.session.scalar(select(User.id).where(User.email == credentials.email)):
            raise AuthProblem("registration_unavailable", 409)
        user = User(email=credentials.email, password_hash=passwords.hash(credentials.password))
        self.session.add(user)
        try:
            self.session.flush()
            result = self._start_session(user)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise AuthProblem("registration_unavailable", 409) from error
        return result

    def login(self, credentials: CredentialsRequest) -> AuthResult:
        user = self.session.scalar(select(User).where(User.email == credentials.email))
        if not passwords.verify(user.password_hash if user else None, credentials.password):
            raise AuthProblem("invalid_credentials", 401)
        assert user is not None and user.password_hash is not None
        if passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash(credentials.password)
        result = self._start_session(user)
        self.session.commit()
        return result

    def refresh(self, raw_token: str) -> AuthResult:
        session_id, secret = parse_refresh_token(raw_token)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.id == session_id).with_for_update()
        )
        now = utc_now()
        if (
            auth_session is None
            or auth_session.revoked_at is not None
            or auth_session.refresh_expires_at <= now
            or not refresh_matches(auth_session.refresh_token_hash, secret)
        ):
            raise AuthProblem("invalid_refresh_session", 401)
        user = self.session.get(User, auth_session.user_id)
        if user is None:
            raise AuthProblem("invalid_refresh_session", 401)
        refresh_token, token_hash = new_refresh_token(auth_session.id)
        auth_session.refresh_token_hash = token_hash
        access_token = issue_access_token(self.settings, user.id, auth_session.id, now=now)
        self.session.commit()
        return AuthResult(user, access_token, refresh_token)

    def revoke_refresh(self, raw_token: str) -> None:
        session_id, secret = parse_refresh_token(raw_token)
        auth_session = self.session.scalar(
            select(AuthSession).where(AuthSession.id == session_id).with_for_update()
        )
        if (
            auth_session
            and auth_session.revoked_at is None
            and auth_session.refresh_expires_at > utc_now()
            and refresh_matches(auth_session.refresh_token_hash, secret)
        ):
            auth_session.revoked_at = utc_now()
        self.session.commit()

    def _start_session(self, user: User) -> AuthResult:
        now = utc_now()
        auth_session = AuthSession(
            user_id=user.id,
            refresh_token_hash="pending",
            refresh_expires_at=now + timedelta(days=self.settings.auth_refresh_token_days),
        )
        self.session.add(auth_session)
        self.session.flush()
        refresh_token, token_hash = new_refresh_token(auth_session.id)
        auth_session.refresh_token_hash = token_hash
        access_token = issue_access_token(self.settings, user.id, auth_session.id, now=now)
        return AuthResult(user, access_token, refresh_token)
