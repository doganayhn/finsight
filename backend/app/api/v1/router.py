from fastapi import APIRouter

from app.modules.categories.routes import router as category_router
from app.modules.imports.routes import router as import_router
from app.modules.transactions.routes import router as transaction_router

router = APIRouter(prefix="/api/v1")
router.include_router(import_router)
router.include_router(category_router)
router.include_router(transaction_router)


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Application liveness; deliberately independent of database availability."""
    return {"status": "ok"}
