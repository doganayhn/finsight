import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.api.v1.router import router
from app.core.config import Settings, get_settings
from app.core.version import APP_VERSION
from app.modules.analytics.service import AnalyticsProblem
from app.modules.assistant.service import AssistantProblem
from app.modules.auth.errors import AuthProblem
from app.modules.auth.rate_limit import FixedWindowLimiter
from app.modules.imports.errors import ImportProblem
from app.modules.transactions.classification import ClassificationProblem


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="FinSight",
        version=APP_VERSION,
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Authorization", "Content-Type"],
    )
    app.state.settings = settings
    app.state.auth_rate_limiter = FixedWindowLimiter(
        settings.auth_rate_limit_requests,
        settings.auth_rate_limit_window_seconds,
        settings.auth_rate_limit_max_keys,
    )
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.max_upload_bytes + 65536)

    logger = logging.getLogger("finsight.requests")

    @app.middleware("http")
    async def security_boundary(request: Request, call_next):
        # Always generate server-side; arbitrary caller request IDs are never trusted.
        request_id = str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        logger.info(
            "request_completed request_id=%s method=%s status=%s",
            request_id,
            request.method,
            response.status_code,
        )
        return response

    @app.exception_handler(AuthProblem)
    async def auth_problem(request, error):
        headers = {"WWW-Authenticate": "Bearer"} if error.status == 401 else None
        return JSONResponse(
            status_code=error.status,
            content={"detail": {"code": error.code}},
            headers=headers,
        )

    @app.exception_handler(ImportProblem)
    async def import_problem(request, error):
        detail = {"code": error.code}
        if error.batch_id:
            detail["import_batch_id"] = str(error.batch_id)
        return JSONResponse(status_code=error.status, content={"detail": detail})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        # Pydantic errors can echo submitted values. Do not return them for financial uploads.
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request"}})

    @app.exception_handler(ClassificationProblem)
    async def classification_problem(request, error):
        return JSONResponse(status_code=error.status, content={"detail": {"code": error.code}})

    @app.exception_handler(AnalyticsProblem)
    async def analytics_problem(request, error):
        return JSONResponse(status_code=error.status, content={"detail": {"code": error.code}})

    @app.exception_handler(AssistantProblem)
    async def assistant_problem(request, error):
        return JSONResponse(status_code=error.status, content={"detail": {"code": error.code}})

    @app.exception_handler(SQLAlchemyError)
    async def persistence_error(request, error):
        # SQLAlchemy errors can contain SQL parameters (descriptions). Do not log/serialize them.
        return JSONResponse(status_code=500, content={"detail": {"code": "persistence_failed"}})

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        # Log only the exception class and request ID; payloads and exception strings
        # may be sensitive.
        logger.error(
            "request_failed request_id=%s error_type=%s",
            getattr(request.state, "request_id", "unavailable"),
            type(error).__name__,
        )
        return JSONResponse(status_code=500, content={"detail": {"code": "internal_error"}})

    app.include_router(router)
    return app
