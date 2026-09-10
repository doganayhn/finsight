from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth
from app.db.session import get_session
from app.modules.auth.errors import AuthProblem
from app.modules.auth.schemas import CredentialsRequest, TokenResponse, UserResponse
from app.modules.auth.security import REFRESH_COOKIE_NAME, REFRESH_COOKIE_PATH
from app.modules.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(request: Request, session: Annotated[Session, Depends(get_session)]) -> AuthService:
    return AuthService(session, request.app.state.settings)


Service = Annotated[AuthService, Depends(_service)]


def _rate_limit(request: Request, action: str) -> None:
    host = request.client.host if request.client else "unknown"
    request.app.state.auth_rate_limiter.check(f"{action}:{host}")


def _trusted_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in request.app.state.settings.cors_origins:
        raise AuthProblem("untrusted_origin", 403)


def _set_refresh_cookie(response: Response, request: Request, result: AuthResult) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        result.refresh_token,
        max_age=settings.auth_refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.auth_refresh_cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


def _response(result: AuthResult) -> TokenResponse:
    return TokenResponse(
        access_token=result.access_token, user=UserResponse.model_validate(result.user)
    )


@router.post("/register", response_model=TokenResponse, status_code=201)
def register(
    body: CredentialsRequest, request: Request, response: Response, service: Service
) -> TokenResponse:
    _rate_limit(request, "register")
    result = service.register(body)
    _set_refresh_cookie(response, request, result)
    return _response(result)


@router.post("/login", response_model=TokenResponse)
def login(
    body: CredentialsRequest, request: Request, response: Response, service: Service
) -> TokenResponse:
    _rate_limit(request, "login")
    result = service.login(body)
    _set_refresh_cookie(response, request, result)
    return _response(result)


@router.post("/refresh", response_model=TokenResponse)
def refresh(request: Request, response: Response, service: Service) -> TokenResponse:
    _trusted_origin(request)
    _rate_limit(request, "refresh")
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_token:
        raise AuthProblem("invalid_refresh_session", 401)
    result = service.refresh(raw_token)
    _set_refresh_cookie(response, request, result)
    return _response(result)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, service: Service) -> None:
    _trusted_origin(request)
    raw_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_token:
        try:
            service.revoke_refresh(raw_token)
        except AuthProblem:
            # Logout remains idempotent while the cookie is always removed.
            service.session.rollback()
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        httponly=True,
        secure=request.app.state.settings.auth_refresh_cookie_secure,
        samesite="lax",
        path=REFRESH_COOKIE_PATH,
    )


@router.get("/me", response_model=UserResponse)
def me(principal: CurrentAuth) -> UserResponse:
    return UserResponse.model_validate(principal.user)
