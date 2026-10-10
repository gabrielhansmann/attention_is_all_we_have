from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.config import get_settings

from .schemas import HealthResponse

router = APIRouter(tags=["health"])


def check_db() -> str:
    """'ok', 'unavailable' or 'not_configured'. Never raises and never exposes the connection string."""
    if not get_settings().db_url:
        return "not_configured"
    try:
        from app.knowledge import tools

        tools._conn().execute("select 1").fetchone()
        return "ok"
    except Exception:
        return "unavailable"


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    db = check_db()
    key = get_settings().openai_api_key_set
    return HealthResponse(status="ok" if db == "ok" and key else "degraded", db=db, openai_key=key,
                          version=__version__)
