"""Evidence library endpoints: loaded sources, coverage, and the upload that adds a source file."""
from __future__ import annotations

from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool

from app.ingest import upload
from app.knowledge import library

from .deps import get_ingest_conn
from .schemas import CoverageOut, SourceOut, UploadOut

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


async def _body(request: Request) -> bytes:
    """The raw request body, refused as soon as it is larger than an upload may be."""
    too_large = HTTPException(status_code=413, detail=f"file too large (limit {upload.MAX_BYTES // 2**20} MB)")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > upload.MAX_BYTES:
        raise too_large
    buf = bytearray()
    async for part in request.stream():
        buf += part
        if len(buf) > upload.MAX_BYTES:
            raise too_large
    if not buf:
        raise HTTPException(status_code=422, detail="the file is empty")
    return bytes(buf)


@router.post("/sources", response_model=UploadOut, status_code=201)
async def upload_source(request: Request, conn: Annotated[psycopg.Connection, Depends(get_ingest_conn)],
                        filename: Annotated[str, Query(min_length=1, max_length=200)],
                        line: Annotated[str | None, Query(max_length=20)] = None, replace: bool = False):
    """Load one PDF or Excel file into the evidence store. The request body is the file itself
    (application/octet-stream). Answers when the file is stored, which takes up to a minute or two for a large
    feedback export because every comment is embedded."""
    data = await _body(request)
    try:
        return await run_in_threadpool(upload.ingest_upload, conn, filename, data, line=line or None, replace=replace)
    except upload.UploadError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception as e:
        raise _unavailable(e)


@router.get("/evidence/coverage", response_model=CoverageOut)
def coverage():
    """Customer comments, study cells and 2025 sales per vehicle line and market, so gaps are visible."""
    try:
        return library.coverage()
    except Exception as e:
        raise _unavailable(e)
