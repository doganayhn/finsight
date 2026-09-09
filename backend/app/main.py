from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.body_limit import RequestBodyLimitMiddleware

from app.api.v1.router import router
from app.core.config import Settings, get_settings
from app.modules.analytics.service import AnalyticsProblem
from app.modules.assistant.service import AssistantProblem
from app.modules.imports.errors import ImportProblem
from app.modules.transactions.classification import ClassificationProblem


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="FinSight",
        version="0.1.0",
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_url="/api/v1/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Accept", "Content-Type", "X-Dev-User-ID"],
    )
    app.state.settings = settings
    app.add_middleware(RequestBodyLimitMiddleware, max_body_size=settings.max_upload_bytes + 65536)

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
        return JSONResponse(
            status_code=500, content={"detail": {"code": "import_persistence_failed"}}
        )

    app.include_router(router)
    return app
