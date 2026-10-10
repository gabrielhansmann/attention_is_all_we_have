"""Chat and plan persistence: conversations, messages, runs and planned steps.

Every function takes an open psycopg connection (dict rows) and does NOT commit; the caller decides.
A request is planned before anything is written, so a planner failure leaves no partial state.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from .catalog import get as agent_spec
from .planner import PlanProposal, Planner, check_edited_plan

DEFAULT_TITLE = "New research request"


class ConversationNotFound(LookupError):
    pass


class RunNotFound(LookupError):
    pass


class ConversationArchived(ValueError):
    pass


class PlanLocked(ValueError):
    """The plan can only be edited while every step is still `planned`."""


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


# ---------------------------------------------------------------- planning

def _plan_payload(run: dict, steps: list[dict]) -> dict:
    return {
        "run_id": str(run["id"]), "vehicle_line": run["vehicle_line"], "market": run["market"],
        "steps": [{"step_id": str(s["id"]), "position": s["position"], "agent": s["agent_name"], "stage": s["stage"],
                   "reason": s["plan_reason"], "planned_by": s["planned_by"], "available": agent_spec(s["agent_name"]).available}
                  for s in steps],
    }


def _plan_text(run: dict, steps: list[dict]) -> str:
    scope = f"{run['vehicle_line'] if run['vehicle_line'] != 'ALL' else 'all lines'}, " \
            f"{run['market'] if run['market'] != 'ALL' else 'all markets'}"
    lines = [f"Plan ({scope}). Agents run one at a time and each answer waits for your review:"]
    for s in steps:
        tail = "" if agent_spec(s["agent_name"]).available else " [not built yet]"
        lines.append(f"{s['position']}. {s['agent_name']}{tail}" + (f": {s['plan_reason']}" if s["plan_reason"] else ""))
    return "\n".join(lines)


def _insert_steps(conn, run_id: UUID, agents: list[tuple[str, str, str]]) -> list[dict]:
    """agents: (name, reason, planned_by) in order. Each step depends on the one before it."""
    steps: list[dict] = []
    prev: UUID | None = None
    for position, (name, reason, planned_by) in enumerate(agents, 1):
        row = conn.execute(
            "insert into public.step (run_id, agent_name, stage, depends_on_step_ids, position, plan_reason, planned_by) "
            "values (%s,%s,%s,%s,%s,%s,%s) returning *",
            (run_id, name, agent_spec(name).stage, [prev] if prev else [], position, reason or None, planned_by)).fetchone()
        steps.append(row)
        prev = row["id"]
    return steps


def post_request(conn, conversation_id: UUID, text: str, planner: Planner, actor: str = "pm") -> dict:
    """Store the PM's request, let the planner choose agents, and store the plan as `planned` steps.
    Returns {"messages": [...], "run": run-with-steps | None}."""
    conv = get_conversation(conn, conversation_id)
    if conv["status"] != "active":
        raise ConversationArchived("this conversation is archived")
    proposal: PlanProposal = planner.plan(text)          # may raise PlannerError before any write

    messages = [add_message(conn, conversation_id, "pm", "request", text, payload={"author": actor})]
    if not proposal.steps:
        messages.append(add_message(
            conn, conversation_id, "orchestrator", "system_note",
            "I could not tell which agents are needed for that. Ask about a vehicle line, a market, competitors, "
            "trends, options or customer feedback, or ask for requirements."))
        return {"messages": messages, "run": None}

    run = conn.execute(
        "insert into public.pipeline_run (trigger, vehicle_line, market, query_text, created_by, conversation_id) "
        "values ('pm_query', %s, %s, %s, %s, %s) returning *",
        (proposal.vehicle_line or "ALL", proposal.market or "ALL", text, actor, conversation_id)).fetchone()
    steps = _insert_steps(conn, run["id"], [(s.agent, s.reason, "orchestrator") for s in proposal.steps])
    run["steps"] = [{**s, "available": agent_spec(s["agent_name"]).available} for s in steps]

    messages.append(add_message(conn, conversation_id, "orchestrator", "plan", _plan_text(run, steps),
                                run_id=run["id"], payload=_plan_payload(run, steps)))
    missing = proposal.unavailable
    if missing:
        messages.append(add_message(
            conn, conversation_id, "orchestrator", "system_note",
            f"Not built yet: {', '.join(missing)}. The plan keeps them so you can see what the question needs, "
            "but they cannot run until they exist. You can remove them from the plan.", run_id=run["id"]))

    conn.execute(
        "update public.conversation set title = case when title = %s then %s else title end, "
        "vehicle_line = coalesce(vehicle_line, %s), market_code = coalesce(market_code, %s) where id = %s",
        (DEFAULT_TITLE, proposal.title[:120], proposal.vehicle_line, proposal.market, conversation_id))
    _audit(conn, run["id"], "orchestrator", "plan_created", {**_plan_payload(run, steps), "requested_by": actor},
           "Agents chosen from the request by the planner")
    return {"messages": messages, "run": run}


def edit_plan(conn, run_id: UUID, agent_names: list[str], actor: str = "pm") -> dict:
    """Replace the plan of a run whose steps are all still `planned`. Raises PlanError for an invalid plan."""
    run = conn.execute("select * from public.pipeline_run where id = %s for update", (run_id,)).fetchone()
    if not run:
        raise RunNotFound(str(run_id))
    old = list_steps(conn, run_id)
    if any(s["status"] != "planned" for s in old):
        raise PlanLocked("the plan can no longer be edited: an agent has already started")
    new = check_edited_plan(agent_names)

    reasons = {s["agent_name"]: s["plan_reason"] for s in old}
    removed = [s["agent_name"] for s in old if s["agent_name"] not in agent_names]
    added = [p.agent for p in new if p.agent not in reasons]
    conn.execute("delete from public.step where run_id = %s", (run_id,))
    steps = _insert_steps(conn, run_id, [(p.agent, reasons.get(p.agent) or "Added by the PM.",
                                          "orchestrator" if p.agent in reasons else "pm") for p in new])
    run["steps"] = [{**s, "available": agent_spec(s["agent_name"]).available} for s in steps]

    parts = ([f"removed {', '.join(removed)}"] if removed else []) + ([f"added {', '.join(added)}"] if added else [])
    text = ("Plan updated" + (": " + "; ".join(parts) if parts else " (order only)") + ".\n" + _plan_text(run, steps))
    message = add_message(conn, run["conversation_id"], "pm", "plan_change", text, run_id=run_id,
                          payload={**_plan_payload(run, steps), "removed": removed, "added": added,
                                   "author": actor})
    _audit(conn, run_id, actor, "plan_edited", {"removed": removed, "added": added,
                                              "steps": [s["agent_name"] for s in steps]})
    return {"messages": [message], "run": run}
