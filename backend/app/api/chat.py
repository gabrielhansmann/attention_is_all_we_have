"""Chat endpoints: conversations, requests, the orchestrator's plan, plan edits, and the PM's actions on a step."""
from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Annotated, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.orchestration import runner, service
from app.orchestration.agents import AgentRunner
from app.orchestration.catalog import CATALOG
from app.orchestration.planner import PlanError, Planner, PlannerError

from .deps import get_conn, get_connect, get_planner, get_runners
from .schemas import (AgentOut, ConversationDetail, ConversationOut, CreateConversation, EditPlan, EditStep, PostMessage,
                      PostResult, RejectStep, RetryStep, StepNote, UpdateConversation)

router = APIRouter(tags=["chat"])
Conn = Annotated[psycopg.Connection, Depends(get_conn)]
Plan = Annotated[Planner, Depends(get_planner)]
Connect = Annotated[Callable[[], AbstractContextManager[psycopg.Connection]], Depends(get_connect)]
Runners = Annotated[dict[str, AgentRunner], Depends(get_runners)]


def _http(e: Exception) -> HTTPException:
    if isinstance(e, (service.ConversationNotFound, service.RunNotFound, runner.StepNotFound)):
        return HTTPException(404, "not found")
    if isinstance(e, (service.ConversationArchived, service.PlanLocked, runner.StepConflict)):
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


# ---------------------------------------------------------------- running the plan

def _execute(step_id: UUID, connect: Callable[[], AbstractContextManager[psycopg.Connection]],
             runners: dict[str, AgentRunner]) -> None:
    with connect() as conn:
        runner.execute_step(conn, step_id, runners)


def _apply(action: Callable[[], dict], conn: psycopg.Connection, background: BackgroundTasks, connect, runners) -> dict:
    """Commit the PM's action, then run the step it started after the response is sent. The agent can take
    minutes; the thread shows the step as `running` until its card arrives."""
    try:
        result = action()
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise _http(e)
    if result["start_step_id"]:
        background.add_task(_execute, result["start_step_id"], connect, runners)
    return result


@router.post("/runs/{run_id}/start", response_model=PostResult)
def start_run(run_id: UUID, conn: Conn, background: BackgroundTasks, connect: Connect, runners: Runners):
    """The PM confirms the plan and the first agent starts. From here on the plan is locked."""
    return _apply(lambda: runner.start_run(conn, run_id), conn, background, connect, runners)


@router.post("/steps/{step_id}/accept", response_model=PostResult)
def accept_step(step_id: UUID, body: StepNote, conn: Conn, background: BackgroundTasks, connect: Connect,
                runners: Runners):
    """Accept the step. This is what starts the next agent, or compiles the final result after the last one."""
    return _apply(lambda: runner.accept(conn, step_id, body.note), conn, background, connect, runners)


@router.post("/steps/{step_id}/retry", response_model=PostResult)
def retry_step(step_id: UUID, body: RetryStep, conn: Conn, background: BackgroundTasks, connect: Connect,
               runners: Runners):
    """Re-run the same agent with a steering note."""
    return _apply(lambda: runner.retry(conn, step_id, body.note), conn, background, connect, runners)


@router.post("/steps/{step_id}/reject", response_model=PostResult)
def reject_step(step_id: UUID, body: RejectStep, conn: Conn, background: BackgroundTasks, connect: Connect,
                runners: Runners):
    """Reject the step, then go on without this agent or abort the run."""
    return _apply(lambda: runner.reject(conn, step_id, body.note, body.proceed), conn, background, connect, runners)


@router.post("/steps/{step_id}/edit", response_model=PostResult)
def edit_step(step_id: UUID, body: EditStep, conn: Conn, background: BackgroundTasks, connect: Connect,
              runners: Runners):
    """Rewrite the step's summary before accepting it. The step stays in review."""
    return _apply(lambda: runner.edit(conn, step_id, body.summary, body.note), conn, background, connect, runners)
