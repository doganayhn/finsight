from fastapi import APIRouter

router = APIRouter(prefix="/api/v1")


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Application liveness; deliberately independent of database availability."""
    return {"status": "ok"}
