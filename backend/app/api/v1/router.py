from fastapi import APIRouter

from app.modules.accounts.routes import router as account_router
from app.modules.analytics.routes import router as analytics_router
from app.modules.categories.routes import router as category_router
from app.modules.imports.history import router as history_router
from app.modules.imports.routes import router as import_router
from app.modules.transactions.routes import router as transaction_router

router = APIRouter(prefix="/api/v1")
router.include_router(account_router)
router.include_router(history_router)
router.include_router(import_router)
router.include_router(category_router)
router.include_router(transaction_router)
router.include_router(analytics_router)


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Application liveness; deliberately independent of database availability."""
    return {"status": "ok"}
