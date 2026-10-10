"""Chat persistence: conversations, messages and runs.

Every function takes an open psycopg connection (dict rows) and does NOT commit; the caller decides.
A request is scoped before anything is written, so an orchestrator failure leaves no partial state. The agents
are called afterwards, by the loop in `loop.py` (decision 0018).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .catalog import get as agent_spec
from .orchestrator import Orchestrator

DEFAULT_TITLE = "New research request"


class ConversationNotFound(LookupError):
    pass


class RunNotFound(LookupError):
    pass


class ConversationArchived(ValueError):
    pass


class RunInProgress(ValueError):
    """One request at a time per conversation: the previous run has not finished."""


# ---------------------------------------------------------------- conversations and messages

def create_conversation(conn, title: str | None = None, actor: str = "pm") -> dict:
    return conn.execute("insert into public.conversation (title, created_by) values (%s, %s) returning *",
                        ((title or DEFAULT_TITLE).strip()[:120], actor)).fetchone()


def list_conversations(conn, status: str = "active", limit: int = 50) -> list[dict]:
    return conn.execute("select * from public.conversation where status = %s order by updated_at desc limit %s",
                        (status, limit)).fetchall()


def get_conversation(conn, conversation_id: UUID) -> dict:
    row = conn.execute("select * from public.conversation where id = %s", (conversation_id,)).fetchone()
    if not row:
        raise ConversationNotFound(str(conversation_id))
    return row


def update_conversation(conn, conversation_id: UUID, *, title: str | None = None, status: str | None = None) -> dict:
    get_conversation(conn, conversation_id)
    return conn.execute(
        "update public.conversation set title = coalesce(%s, title), status = coalesce(%s, status) "
        "where id = %s returning *", (title and title.strip()[:120], status, conversation_id)).fetchone()


def list_messages(conn, conversation_id: UUID) -> list[dict]:
    return conn.execute("select * from public.message where conversation_id = %s order by seq",
                        (conversation_id,)).fetchall()


def list_runs(conn, conversation_id: UUID) -> list[dict]:
    runs = conn.execute("select * from public.pipeline_run where conversation_id = %s order by created_at, id",
                        (conversation_id,)).fetchall()
    for run in runs:
        run["steps"] = list_steps(conn, run["id"])
    return runs


def list_steps(conn, run_id: UUID) -> list[dict]:
    steps = conn.execute("select * from public.step where run_id = %s order by position", (run_id,)).fetchall()
    for s in steps:
        s["available"] = agent_spec(s["agent_name"]).available
    return steps


def add_message(conn, conversation_id: UUID, role: str, kind: str, content: str, *, run_id: UUID | None = None,
                step_id: UUID | None = None, payload: dict | None = None) -> dict:
    return conn.execute(
        "insert into public.message (conversation_id, role, kind, content, run_id, step_id, payload) "
        "values (%s,%s,%s,%s,%s,%s,%s) returning *",
        (conversation_id, role, kind, content, run_id, step_id, Jsonb(payload or {}))).fetchone()


def _audit(conn, run_id: UUID, actor: str, action: str, after: dict, rationale: str | None = None) -> None:
    conn.execute(
        "insert into public.audit_event (entity_type, entity_id, actor, action, after, rationale) "
        "values ('pipeline_run', %s, %s, %s, %s, %s)", (run_id, actor, action, Jsonb(after), rationale))


# ---------------------------------------------------------------- starting a run

def post_request(conn, conversation_id: UUID, text: str, orchestrator: Orchestrator, actor: str = "pm") -> dict:
    """Store the PM's request and open a run for it. The caller commits, then starts the loop for `run`.
    Returns {"messages": [...], "run": run-with-steps}."""
    conv = get_conversation(conn, conversation_id)
    if conv["status"] != "active":
        raise ConversationArchived("this conversation is archived")
    if conn.execute("select 1 from public.pipeline_run where conversation_id = %s and status = 'in_progress'",
                    (conversation_id,)).fetchone():
        raise RunInProgress("the previous request is still being worked on")
    scope = orchestrator.scope(text)          # may raise OrchestratorError before any write

    messages = [add_message(conn, conversation_id, "pm", "request", text, payload={"author": actor})]
    run = conn.execute(
        "insert into public.pipeline_run (trigger, vehicle_line, market, query_text, created_by, conversation_id) "
        "values ('pm_query', %s, %s, %s, %s, %s) returning *",
        (scope.vehicle_line or "ALL", scope.market or "ALL", text, actor, conversation_id)).fetchone()
    run["steps"] = []
    conn.execute(
        "update public.conversation set title = case when title = %s then %s else title end, "
        "vehicle_line = coalesce(vehicle_line, %s), market_code = coalesce(market_code, %s) where id = %s",
        (DEFAULT_TITLE, scope.title[:120], scope.vehicle_line, scope.market, conversation_id))
    _audit(conn, run["id"], "orchestrator", "run_started",
           {"vehicle_line": run["vehicle_line"], "market": run["market"], "requested_by": actor},
           "The orchestrator chooses agents one at a time from the request and the results so far")
    return {"messages": messages, "run": run}
