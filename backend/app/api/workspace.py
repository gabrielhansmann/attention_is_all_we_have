"""Authenticated views and reviews of real persisted workspace data."""
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.knowledge import workspace
from .deps import User, get_conn
from .schemas import ReviewRequirement, WorkspaceConfigOut, WorkspaceSnapshotOut

router = APIRouter(tags=["workspace"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]


def _error(e: Exception) -> HTTPException:
    if isinstance(e, workspace.UnknownScope):
        return HTTPException(422, str(e))
    if isinstance(e, workspace.RequirementNotFound):
        return HTTPException(404, "requirement not found")
    if isinstance(e, workspace.ReviewConflict):
        return HTTPException(409, str(e))
    return HTTPException(503, f"workspace unavailable ({type(e).__name__})")


@router.get("/workspace/config", response_model=WorkspaceConfigOut)
def config(conn: Conn):
    try:
        return workspace.config(conn)
    except Exception as e:
        raise _error(e)


@router.get("/workspace", response_model=WorkspaceSnapshotOut)
def snapshot(conn: Conn, line: Annotated[str | None, Query(min_length=1, max_length=60)] = None,
             market: Annotated[str | None, Query(min_length=1, max_length=60)] = None):
    try:
        return workspace.snapshot(conn, line, market)
    except Exception as e:
        raise _error(e)


@router.patch("/requirements/{requirement_id}/status")
def review(requirement_id: UUID, body: ReviewRequirement, conn: Conn, user: User):
    try:
        result = workspace.review_requirement(conn, requirement_id, body.status, body.expected_status,
                                              body.reason, user["email"])
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise _error(e)
