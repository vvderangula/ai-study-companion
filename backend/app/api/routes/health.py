from fastapi import APIRouter

from app.core import db as dbm
from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    try:
        dbm.get_db().command("ping")
        db_ok = True
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "app": settings.app_name, "environment": settings.environment, "database": db_ok}
