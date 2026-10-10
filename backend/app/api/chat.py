"""Chat endpoints: conversations and requests. A request starts the orchestrator, which calls agents on its own."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.orchestration import loop, runner, service
from app.orchestration.agents import AgentRunner
from app.orchestration.catalog import CATALOG
from app.orchestration.orchestrator import Orchestrator, OrchestratorError

from .deps import User, get_checkpointer, get_conn, get_connect, get_orchestrator, get_runners
from .schemas import AgentOut, ConversationDetail, ConversationOut, CreateConversation, PostMessage, PostResult, UpdateConversation

router = APIRouter(tags=["chat"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Orchestrate = Annotated[Orchestrator, Depends(get_orchestrator)]
Connect = Annotated[Callable[[], AbstractContextManager[psycopg.Connection]], Depends(get_connect)]
Runners = Annotated[dict[str, AgentRunner], Depends(get_runners)]
Checkpoints = Annotated[loop.CheckpointerFactory, Depends(get_checkpointer)]


def _http(e: Exception) -> HTTPException:
    from app.knowledge.models import ModelNotFound
    if isinstance(e, ModelNotFound):
        return HTTPException(404, str(e))
    if isinstance(e, (service.ConversationNotFound, service.RunNotFound, runner.StepNotFound)):
        return HTTPException(404, "not found")
    if isinstance(e, (service.ConversationArchived, service.RunInProgress, runner.StepConflict)):
        return HTTPException(409, str(e))
    if isinstance(e, OrchestratorError):
        return HTTPException(503, f"orchestrator unavailable: {e}")
    if isinstance(e, psycopg.Error):
        return HTTPException(503, f"database error ({type(e).__name__})")
    if isinstance(e, ValueError):
        return HTTPException(422, str(e))
    raise e


def _detail(conn, conversation_id: UUID) -> ConversationDetail:
    return ConversationDetail(conversation=service.get_conversation(conn, conversation_id),
                              messages=service.list_messages(conn, conversation_id),
                              runs=service.list_runs(conn, conversation_id))


@router.get("/agents", response_model=list[AgentOut])
def agents() -> list[AgentOut]:
    """The agents the orchestrator can call, in pipeline order, and which of them exist yet."""
    return [AgentOut(name=a.name, stage=a.stage, description=a.description, available=a.available) for a in CATALOG]


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(conn: Conn, status: Literal["active", "archived"] = "active",
                       limit: Annotated[int, Query(ge=1, le=100)] = 50):
    try:
        return service.list_conversations(conn, status, limit)
    except Exception as e:
        raise _http(e)


@router.post("/conversations", response_model=ConversationDetail, status_code=201)
def create_conversation(body: CreateConversation, conn: Conn, background: BackgroundTasks, connect: Connect,
                        orchestrator: Orchestrate, runners: Runners, checkpointer: Checkpoints, user: User):
    try:
        conv = service.create_conversation(conn, body.title, user["email"], model_id=body.comparison_model_id,
                                           variant=body.comparison_variant, market=body.comparison_market)
        started = service.post_request(conn, conv["id"], body.request, orchestrator, user["email"]) if body.request else None
        conn.commit()
        detail = _detail(conn, conv["id"])
    except Exception as e:
        conn.rollback()
        raise _http(e)
    if started:
        background.add_task(loop.orchestrate, connect, started["run"]["id"], orchestrator, runners,
                           checkpointer=checkpointer)
    return detail


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
def post_message(conversation_id: UUID, body: PostMessage, conn: Conn, background: BackgroundTasks, connect: Connect,
                 orchestrator: Orchestrate, runners: Runners, checkpointer: Checkpoints, user: User):
    """A PM request. It is answered at once with the stored request; the orchestrator then works on it in the
    background, calling agents one at a time until it can answer. The thread shows each step as it happens."""
    try:
        result = service.post_request(conn, conversation_id, body.content.strip(), orchestrator, user["email"])
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise _http(e)
    background.add_task(loop.orchestrate, connect, result["run"]["id"], orchestrator, runners,
                       checkpointer=checkpointer)
    return result
