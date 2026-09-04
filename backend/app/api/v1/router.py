from fastapi import APIRouter

from app.modules.imports.routes import router as import_router

router = APIRouter(prefix="/api/v1")
router.include_router(import_router)


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Application liveness; deliberately independent of database availability."""
    return {"status": "ok"}
