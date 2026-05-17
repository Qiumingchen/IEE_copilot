from fastapi import APIRouter, HTTPException

from app.core.config import get_settings
from app.db.session import ping_database


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "iee-copilot-api"}


@router.get("/health/db")
def health_db() -> dict[str, str]:
    settings = get_settings()
    if settings.skip_db_healthcheck:
        return {"database": "skipped"}
    try:
        ping_database()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return {"database": "ok"}
