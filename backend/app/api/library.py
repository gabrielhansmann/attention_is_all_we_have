"""Evidence library endpoints: loaded sources and coverage. Read-only."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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
    """Customer comments, study cells and 2025 sales per vehicle line and market, so gaps are visible."""
    try:
        return library.coverage()
    except Exception as e:
        raise _unavailable(e)


@router.get("/sources/{source_id}/file")
def source_file(source_id: UUID):
    """The provided original (PDF or workbook), inline so the browser opens a PDF at `#page=N`."""
    try:
        path, name = library.source_file(str(source_id))
    except LookupError:
        raise HTTPException(status_code=404, detail="source file is not available")
    except Exception as e:
        raise _unavailable(e)
    return FileResponse(path, filename=name, content_disposition_type="inline")
