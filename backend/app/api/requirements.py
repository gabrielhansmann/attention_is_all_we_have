"""Requirements, tracking and dossiers: what the research produced and what the PM decides about it (decision 0022)."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.orchestration import register, tracking

from .deps import User, get_conn

router = APIRouter(tags=["requirements"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]

Status = Literal["draft", "pm_review", "tracked", "rejected", "challenged", "superseded"]
Decision = Literal["approve", "reject", "challenge", "supersede", "reopen", "acknowledge"]


class RequirementOut(BaseModel):
    id: UUID
    code: str
    run_id: UUID | None
    conversation_id: UUID | None
    vehicle_line: str
    market: str
    title: str
    status: Status
    payload: dict[str, Any]
    score: dict[str, Any] | None
    decided_by: str | None
    decided_at: datetime | None
    decision_note: str | None
    tracked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    actions: list[Decision]
    flags: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []       # the findings the requirement cites, with their sources


class EventOut(BaseModel):
    id: UUID
    actor: str
    action: str
    rationale: str | None
    timestamp: datetime
    after: dict[str, Any] | None = None


class RequirementDetail(RequirementOut):
    history: list[EventOut]


class RequirementList(BaseModel):
    requirements: list[RequirementOut]
    counts: dict[str, int]


class DecisionIn(BaseModel):
    action: Decision
    note: str | None = Field(default=None, max_length=1000)


class TrackingCheckIn(BaseModel):
    requirement_ids: list[UUID] | None = None


class TrackingOut(BaseModel):
    requirements: list[RequirementOut]
    last_checked: datetime | None


class TrackingResult(BaseModel):
    checked: int
    summary: str
    flags: list[dict[str, Any]]
    skipped: list[dict[str, str]]
    errors: list[str]


class DossierOut(BaseModel):
    run_id: UUID
    conversation_id: UUID | None
    title: str
    vehicle_line: str
    market: str
    created_at: datetime | None
    dossier: str
    findings: list[dict[str, Any]] = []


def _http(e: Exception) -> HTTPException:
    if isinstance(e, register.RequirementNotFound):
        return HTTPException(404, "no such requirement")
    if isinstance(e, register.InvalidDecision):
        return HTTPException(409, str(e))
    if isinstance(e, psycopg.Error):
        return HTTPException(503, f"database error ({type(e).__name__})")
    raise e


def _with_evidence(conn, rows: list[dict]) -> list[dict]:
    """Attach each requirement's cited findings, read once per run, so a citation can be opened in the source viewer."""
    by_run: dict[UUID, list[dict]] = {}
    for r in rows:
        if r.get("run_id") and r["run_id"] not in by_run:
            by_run[r["run_id"]] = register.run_findings(conn, r["run_id"])
        wanted = {str(i) for i in (r["payload"] or {}).get("linked_finding_ids") or []}
        r["evidence"] = [f for f in by_run.get(r.get("run_id"), []) if str(f.get("id")) in wanted]
    return rows


@router.get("/requirements", response_model=RequirementList)
def list_requirements(conn: Conn, status: Status | None = None, line: str | None = None,
                      run_id: UUID | None = None, conversation_id: UUID | None = None):
    try:
        rows = register.list_requirements(conn, status=status, line=line, run_id=run_id, conversation_id=conversation_id)
        return RequirementList(requirements=_with_evidence(conn, rows), counts=register.counts(conn))
    except Exception as e:
        raise _http(e)


@router.get("/requirements/{requirement_id}", response_model=RequirementDetail)
def get_requirement(requirement_id: UUID, conn: Conn):
    try:
        row = register.get_requirement(conn, requirement_id)
        row["flags"] = tracking.open_flags(conn).get(requirement_id, [])
        return _with_evidence(conn, [row])[0]
    except Exception as e:
        raise _http(e)


@router.post("/requirements/{requirement_id}/decision", response_model=RequirementDetail)
def decide(requirement_id: UUID, body: DecisionIn, conn: Conn, user: User):
    """The PM's decision on one requirement. Reject, challenge and supersede need a reason; it is recorded."""
    try:
        row = register.decide(conn, requirement_id, body.action, user["email"], body.note)
        conn.commit()
        row["flags"] = tracking.open_flags(conn).get(requirement_id, [])
        return _with_evidence(conn, [row])[0]
    except Exception as e:
        conn.rollback()
        raise _http(e)


@router.get("/tracking", response_model=TrackingOut)
def tracked(conn: Conn):
    """Tracked requirements with their open flags, those needing attention first."""
    try:
        flags = tracking.open_flags(conn)
        rows = register.list_requirements(conn, status="tracked")
        for r in rows:
            r["flags"] = flags.get(r["id"], [])
        _with_evidence(conn, rows)
        rows.sort(key=lambda r: -len(r["flags"]))
        return TrackingOut(requirements=rows, last_checked=tracking.last_checked(conn))
    except Exception as e:
        raise _http(e)


@router.post("/tracking/check", response_model=TrackingResult)
def check_tracking(body: TrackingCheckIn, conn: Conn, user: User):
    """Re-read the evidence behind tracked requirements and flag what moved. Flags never change a status."""
    try:
        result = tracking.check(conn, user["email"], body.requirement_ids)
        conn.commit()
        return result
    except HTTPException:
        raise
    except psycopg.Error as e:
        conn.rollback()
        raise _http(e)
    except Exception as e:                       # the evidence search needs the embedding service
        conn.rollback()
        raise HTTPException(503, f"evidence search unavailable ({type(e).__name__})")


@router.get("/dossiers", response_model=list[DossierOut])
def dossiers(conn: Conn):
    try:
        out = register.list_dossiers(conn)
        for d in out:
            d["findings"] = register.run_findings(conn, d["run_id"])
        return out
    except Exception as e:
        raise _http(e)
