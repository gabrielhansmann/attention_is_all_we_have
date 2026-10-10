"""The orchestration loop as a LangGraph graph: ask the orchestrator what to do, call that agent, read its result,
ask again (decisions 0018 and 0019).

    START -> decide -> validate -> run_agent -> decide ...        decide / validate -> finish -> END

It runs after the request that opened the run has been answered (an agent can take minutes) and ends when the
orchestrator finishes, when it keeps asking for calls the rules refuse, or at the call budget. Every decision, agent
result and refusal is written to the thread as it happens, so a person can watch the run and read why each agent was
called. Nobody approves a step.

The graph state holds control flow only (the pending decision, refusals, why the loop is stopping). What happened
lives in the run, step and message tables, and `decide` reads its history from them, so there is one record. The
checkpointer (Postgres, thread id = run id) lets a run that a restart interrupted continue where it was. Each node
is safe to run twice: `run_agent` reuses a step that is still running and never calls an agent twice.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any, TypedDict
from uuid import UUID

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from app.config import get_settings

from . import runner, service
from .agents import AgentRunner
from .catalog import get as agent_spec
from .orchestrator import Orchestrator, OrchestratorError, Outcome, Scope, check_call

log = logging.getLogger(__name__)

Connect = Callable[[], AbstractContextManager[psycopg.Connection]]
CheckpointerFactory = Callable[[], AbstractContextManager[BaseCheckpointSaver]]

MAX_AGENT_CALLS = 8        # every call can mean model and web requests, so the budget is small and fixed
MAX_REFUSED_CALLS = 2      # consecutive calls the rules refused before the loop stops asking

RECURSION_LIMIT = 200      # graph steps: three per agent call plus refusals, far above MAX_AGENT_CALLS * 3

NO_AGENT_NOTE = ("I could not tell which agents are needed for that. Ask about a vehicle line, a market, competitors, "
                 "trends, options or customer feedback, or ask for requirements.")


def _history(conn: psycopg.Connection, run_id: UUID) -> list[Outcome]:
    steps = conn.execute("select * from public.step where run_id = %s order by position", (run_id,)).fetchall()
    return [Outcome(agent=s["agent_name"], stage=s["stage"], accepted=s["status"] == "accepted",
                    summary=s["human_readable_summary"] or "",
                    findings=len((runner._output_of(s) or {}).get("findings") or [])) for s in steps]


def _begin_step(conn: psycopg.Connection, run: dict, agent: str, reason: str, history: list[Outcome]) -> UUID:
    """Record the orchestrator's decision: a `running` step, and a note in the thread saying why."""
    previous = conn.execute("select id from public.step where run_id = %s and status = 'accepted' order by position",
                            (run["id"],)).fetchall()
    step = conn.execute(
        "insert into public.step (run_id, agent_name, stage, depends_on_step_ids, position, plan_reason, planned_by, "
        "status, launched_by, launched_at) values (%s, %s, %s, %s, %s, %s, 'orchestrator', 'running', "
        "'orchestrator', now()) returning *",
        (run["id"], agent, agent_spec(agent).stage, [p["id"] for p in previous], len(history) + 1, reason or None)).fetchone()
    service.add_message(conn, run["conversation_id"], "orchestrator", "system_note",
                        f"Calling {agent}" + (f": {reason}" if reason else "."), run_id=run["id"], step_id=step["id"],
                        payload={"decision": {"agent": agent, "reason": reason, "position": step["position"]}})
    runner._audit(conn, "step", step["id"], "orchestrator", "step_started",
                  after={"agent": agent, "position": step["position"]}, rationale=reason or None)
    return step["id"]


def _note(conn: psycopg.Connection, run: dict, text: str) -> None:
    service.add_message(conn, run["conversation_id"], "orchestrator", "system_note", text, run_id=run["id"])


def _abort(conn: psycopg.Connection, run: dict, text: str) -> None:
    conn.execute("update public.pipeline_run set status = 'aborted' where id = %s", (run["id"],))
    _note(conn, run, text)
    runner._audit(conn, "pipeline_run", run["id"], "orchestrator", "run_aborted", rationale=text)


def _finish(conn: psycopg.Connection, run: dict, stop_note: str | None) -> None:
    steps = service.list_steps(conn, run["id"])
    if not steps:
        _abort(conn, run, NO_AGENT_NOTE)
        return
    if stop_note:
        _note(conn, run, stop_note)
    runner._complete(conn, run, steps, [])


class LoopState(TypedDict, total=False):
    run_id: str
    decision: dict[str, str] | None     # the call waiting to be validated or run: {"agent", "reason"}
    refused: list[str]                  # why the rules refused the last choices, shown to the model
    note: str | None                    # why the loop is stopping, for the thread
    failed: str | None                  # the orchestrator error that stopped the loop
    next: str                           # which node follows; read by the conditional edges


def _load_run(conn: psycopg.Connection, run_id: str) -> dict | None:
    run = conn.execute("select * from public.pipeline_run where id = %s", (run_id,)).fetchone()
    return run if run and run["status"] == "in_progress" else None


def build_graph(connect: Connect, orchestrator: Orchestrator, runners: dict[str, AgentRunner] | None,
                max_calls: int = MAX_AGENT_CALLS) -> StateGraph:
    """The loop as a graph. Dependencies are closed over, not put in the state, because the state is checkpointed."""

    def decide(state: LoopState) -> LoopState:
        with connect() as conn:
            run = _load_run(conn, state["run_id"])
            if run is None:
                return {"next": "end"}
            history = _history(conn, run["id"])
        calls_left = max_calls - len(history)
        if calls_left <= 0:
            return {"next": "finish", "decision": None,
                    "note": f"I stopped after {max_calls} agent calls, the most one request may use."}
        scope = Scope("", None if run["vehicle_line"] == "ALL" else run["vehicle_line"],
                      None if run["market"] == "ALL" else run["market"])
        try:
            decision = orchestrator.decide(run["query_text"] or "", scope, history, state.get("refused") or [], calls_left)
        except OrchestratorError as e:
            return {"next": "finish", "decision": None, "failed": str(e)}
        if decision.action == "finish":
            return {"next": "finish", "decision": None}
        return {"next": "validate", "decision": {"agent": decision.agent or "", "reason": decision.reason}}

    def validate(state: LoopState) -> LoopState:
        with connect() as conn:
            history = _history(conn, UUID(state["run_id"]))
        decision = state.get("decision") or {}
        problem = check_call(decision.get("agent"), history)
        if not problem:
            return {"next": "run_agent", "refused": []}
        refused = [*(state.get("refused") or []), problem]
        if len(refused) > MAX_REFUSED_CALLS:
            return {"next": "finish", "decision": None, "refused": refused,
                    "note": f"I stopped because I kept choosing agents that cannot run now ({problem})."}
        return {"next": "decide", "decision": None, "refused": refused}

    def run_agent(state: LoopState) -> LoopState:
        decision = state.get("decision") or {}
        agent = decision.get("agent") or ""
        with connect() as conn:
            run = _load_run(conn, state["run_id"])
            if run is None:
                return {"next": "end"}
            existing = conn.execute("select id, status from public.step where run_id = %s and agent_name = %s",
                                    (run["id"], agent)).fetchone()
            if existing is None:
                step_id = _begin_step(conn, run, agent, decision.get("reason", ""), _history(conn, run["id"]))
                conn.commit()                  # the step is visible as running while the agent works
            elif existing["status"] == "running":
                step_id = existing["id"]       # a restart interrupted this agent: run it again, not a second step
            else:
                return {"next": "decide", "decision": None}      # it finished before the interruption
            runner.execute_step(conn, step_id, runners)
        return {"next": "decide", "decision": None}

    def finish(state: LoopState) -> LoopState:
        with connect() as conn:
            run = _load_run(conn, state["run_id"])
            if run is not None:
                failed = state.get("failed")
                if failed:
                    reason = f"I could not decide the next step ({failed})."
                    if any(o.accepted for o in _history(conn, run["id"])):
                        _finish(conn, run, f"{reason} Here is what the agents found so far.")
                    else:
                        _abort(conn, run, reason)
                else:
                    _finish(conn, run, state.get("note"))
                conn.commit()
        return {"next": "end"}

    def route(state: LoopState) -> str:
        return state["next"]

    graph = StateGraph(LoopState)
    graph.add_node("decide", decide)
    graph.add_node("validate", validate)
    graph.add_node("run_agent", run_agent)
    graph.add_node("finish", finish)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges("decide", route, {"validate": "validate", "finish": "finish", "end": END})
    graph.add_conditional_edges("validate", route, {"run_agent": "run_agent", "decide": "decide", "finish": "finish"})
    graph.add_conditional_edges("run_agent", route, {"decide": "decide", "end": END})
    graph.add_edge("finish", END)
    return graph


def postgres_checkpointer() -> AbstractContextManager[BaseCheckpointSaver]:
    """The production checkpointer: its own connection to the project database (autocommit, as the saver needs). The
    tables come from the migration `20261014_langgraph_checkpoints.sql`; the saver never creates them."""
    from langgraph.checkpoint.postgres import PostgresSaver
    return PostgresSaver.from_conn_string(get_settings().db_url or "")


def _abort_after_crash(connect: Connect, run_id: UUID, error: Exception) -> None:
    try:
        with connect() as conn:
            conn.rollback()
            run = _load_run(conn, str(run_id))
            if run:
                reason = f"database error ({type(error).__name__})" if isinstance(error, psycopg.Error) else type(error).__name__
                _abort(conn, run, f"The run stopped because of an internal error ({reason}).")
                conn.commit()
    except Exception:
        log.exception("could not mark run %s as aborted", run_id)


def orchestrate(connect: Connect, run_id: UUID, orchestrator: Orchestrator,
                runners: dict[str, AgentRunner] | None = None, max_calls: int = MAX_AGENT_CALLS,
                checkpointer: CheckpointerFactory = postgres_checkpointer, resume_only: bool = False) -> None:
    """Run the graph for one run to its end, or continue it from its last checkpoint. Never raises: a failure ends
    the run with a note a person can read.

    An advisory lock on the run id keeps two processes (or a restart that overlaps its predecessor) from driving
    the same run. With `resume_only`, a run is continued only if it has a checkpoint waiting; a run with steps but no
    checkpoint (from before decision 0019) is left alone."""
    try:
        with connect() as lock_conn:
            locked = lock_conn.execute("select pg_try_advisory_lock(hashtextextended(%s, 0)) as locked",
                                       (str(run_id),)).fetchone()["locked"]
            if not locked:
                return
            try:
                with checkpointer() as saver:
                    graph = build_graph(connect, orchestrator, runners, max_calls).compile(checkpointer=saver)
                    config: Any = {"configurable": {"thread_id": str(run_id)}, "recursion_limit": RECURSION_LIMIT}
                    if graph.get_state(config).next:
                        graph.invoke(None, config)
                    elif resume_only:
                        with connect() as conn:
                            fresh = _load_run(conn, str(run_id)) and not _history(conn, run_id)
                        if fresh:
                            graph.invoke({"run_id": str(run_id), "refused": []}, config)
                    else:
                        graph.invoke({"run_id": str(run_id), "refused": []}, config)
            finally:
                lock_conn.execute("select pg_advisory_unlock(hashtextextended(%s, 0))", (str(run_id),))
    except Exception as error:          # the run must not stay `in_progress` for ever
        log.exception("orchestration of run %s failed", run_id)
        _abort_after_crash(connect, run_id, error)


def resume_unfinished(connect: Connect, orchestrator: Orchestrator, runners: dict[str, AgentRunner] | None = None,
                      checkpointer: CheckpointerFactory = postgres_checkpointer) -> list[threading.Thread]:
    """Continue every run a restart left `in_progress`, each in its own thread. Called when the API starts."""
    with connect() as conn:
        ids = [r["id"] for r in conn.execute(
            "select id from public.pipeline_run where status = 'in_progress' and conversation_id is not null").fetchall()]
    threads = [threading.Thread(target=orchestrate, name=f"resume-{run_id}", daemon=True,
                                args=(connect, run_id, orchestrator, runners, MAX_AGENT_CALLS, checkpointer, True))
               for run_id in ids]
    for t in threads:
        t.start()
    return threads
