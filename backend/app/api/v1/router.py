from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.modules.accounts.routes import router as account_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.assistant.routes import router as assistant_router
from app.modules.auth.routes import router as auth_router
from app.modules.categories.routes import router as category_router
from app.modules.imports.history import router as history_router
from app.modules.imports.routes import router as import_router
from app.modules.transactions.routes import router as transaction_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(account_router)
router.include_router(history_router)
router.include_router(import_router)
router.include_router(category_router)
router.include_router(transaction_router)
router.include_router(analytics_router)
router.include_router(assistant_router)


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Application liveness; deliberately independent of database availability."""
    return {"status": "ok"}


@router.get("/health/live", tags=["health"])
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["health"])
def ready(session: Annotated[Session, Depends(get_session)]):
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}
