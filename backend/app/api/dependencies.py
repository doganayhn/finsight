from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_engine
from app.modules.auth.errors import AuthProblem
from app.modules.auth.models import AuthSession, User
from app.modules.auth.security import decode_access_token, utc_now

bearer = HTTPBearer(auto_error=False)


def get_auth_session():
    """Keep authentication lookup transactions separate from product unit-of-work sessions."""
    with Session(get_engine()) as session:
        yield session


@dataclass(frozen=True)
class AuthPrincipal:
    user_id: UUID
    session_id: UUID
    user: User


def authenticated_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: Annotated[Session, Depends(get_auth_session)],
) -> AuthPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthProblem("authentication_required", 401)
    claims = decode_access_token(request.app.state.settings, credentials.credentials)
    auth_session = session.scalar(
        select(AuthSession)
        .options(joinedload(AuthSession.user))
        .where(
            AuthSession.id == claims.session_id,
            AuthSession.user_id == claims.user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.refresh_expires_at > utc_now(),
        )
    )
    if auth_session is None:
        raise AuthProblem("authentication_required", 401)
    return AuthPrincipal(claims.user_id, claims.session_id, auth_session.user)


CurrentAuth = Annotated[AuthPrincipal, Depends(authenticated_user)]


def current_user_id(principal: CurrentAuth) -> UUID:
    return principal.user_id


UserContext = Annotated[UUID, Depends(current_user_id)]
