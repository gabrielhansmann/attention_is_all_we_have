"""Chat endpoints: conversations, requests, the orchestrator's plan and plan edits."""
from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.orchestration import service
from app.orchestration.catalog import CATALOG
from app.orchestration.planner import PlanError, Planner, PlannerError

from .deps import get_conn, get_planner
from .schemas import (AgentOut, ConversationDetail, ConversationOut, CreateConversation, EditPlan, PostMessage,
                      PostResult, UpdateConversation)

router = APIRouter(tags=["chat"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Plan = Annotated[Planner, Depends(get_planner)]


def _http(e: Exception) -> HTTPException:
    if isinstance(e, (service.ConversationNotFound, service.RunNotFound)):
        return HTTPException(404, "not found")
    if isinstance(e, (service.ConversationArchived, service.PlanLocked)):
        return HTTPException(409, str(e))
    if isinstance(e, PlanError):
        return HTTPException(422, str(e))
    if isinstance(e, PlannerError):
        return HTTPException(503, f"planner unavailable: {e}")
    if isinstance(e, psycopg.Error):
        return HTTPException(503, f"database error ({type(e).__name__})")
    raise e


def _detail(conn, conversation_id: UUID) -> ConversationDetail:
    return ConversationDetail(conversation=service.get_conversation(conn, conversation_id),
                              messages=service.list_messages(conn, conversation_id),
                              runs=service.list_runs(conn, conversation_id))


@router.get("/agents", response_model=list[AgentOut])
def agents() -> list[AgentOut]:
    """The agents the orchestrator can plan, in pipeline order, and which of them exist yet."""
    return [AgentOut(name=a.name, stage=a.stage, description=a.description, available=a.available) for a in CATALOG]


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(conn: Conn, status: Literal["active", "archived"] = "active",
                       limit: Annotated[int, Query(ge=1, le=100)] = 50):
    try:
        return service.list_conversations(conn, status, limit)
    except Exception as e:
        raise _http(e)


@router.post("/conversations", response_model=ConversationDetail, status_code=201)
def create_conversation(body: CreateConversation, conn: Conn, planner: Plan):
    try:
        conv = service.create_conversation(conn, body.title)
        if body.request:
            service.post_request(conn, conv["id"], body.request, planner)
        conn.commit()
        return _detail(conn, conv["id"])
    except Exception as e:
        raise _http(e)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: UUID, conn: Conn):
    try:
        return _detail(conn, conversation_id)
    except Exception as e:
        raise _http(e)


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
def update_conversation(conversation_id: UUID, body: UpdateConversation, conn: Conn):
    try:
        row = service.update_conversation(conn, conversation_id, title=body.title, status=body.status)
        conn.commit()
        return row
    except Exception as e:
        raise _http(e)


@router.post("/conversations/{conversation_id}/messages", response_model=PostResult, status_code=201)
def post_message(conversation_id: UUID, body: PostMessage, conn: Conn, planner: Plan):
    """A PM request: the orchestrator chooses agents and stores the plan (steps stay `planned`)."""
    try:
        result = service.post_request(conn, conversation_id, body.content.strip(), planner)
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise _http(e)


@router.put("/runs/{run_id}/plan", response_model=PostResult)
def edit_plan(run_id: UUID, body: EditPlan, conn: Conn):
    """Replace the plan while no agent has started. The PM's edit is checked, never silently completed."""
    try:
        result = service.edit_plan(conn, run_id, body.agents)
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        raise _http(e)
