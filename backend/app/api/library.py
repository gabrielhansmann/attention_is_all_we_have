"""Evidence library endpoints: loaded sources and coverage. Read-only."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.knowledge import library

from .schemas import CoverageOut, SourceOut

router = APIRouter(tags=["library"])


def _unavailable(e: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=f"evidence store unavailable ({type(e).__name__})")


@router.get("/sources", response_model=list[SourceOut])
def sources():
    """Every loaded source file with what was extracted from it."""
    try:
        return library.list_sources()
    except Exception as e:
        raise _unavailable(e)


@router.get("/evidence/coverage", response_model=CoverageOut)
def coverage():
    """Customer comments, study cells and latest recorded sales per scope, so gaps are visible."""
    try:
        return library.coverage()
    except Exception as e:
        raise _unavailable(e)
