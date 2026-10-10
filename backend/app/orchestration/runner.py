"""Step runner: runs one agent behind the Critic and records the result (docs/architecture/02, decision 0018).

The transition rules live in `steps.py`; the loop that decides which agent runs next is in `loop.py`. This module is
the I/O around a single step. Nobody approves a step: the Critic is the automatic reviewer, and the orchestrator
reads the outcome before choosing the next call.

A step's output is kept as JSON on the step (`structured_output_refs`), after the Critic's adjustments. Later
steps read the accepted output from there, so nothing a failed step produced can reach them.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from app.agents import critic_agent as critic

from . import register, service
from .agents import RUNNERS, AgentRunner, StepContext
from .steps import InvalidTransition, StepAction, StepStatus, next_status

log = logging.getLogger(__name__)

MAX_CRITIC_RETRIES = 1        # each automatic retry re-runs the agent (model and web calls), so keep it small
DOCUMENTATION_AGENT = "Documentation Agent"


class StepNotFound(LookupError):
    pass


class StepConflict(ValueError):
    """The step or its run is not in a state that allows this."""


# ---------------------------------------------------------------- helpers

def _audit(conn, entity_type: str, entity_id: UUID, actor: str, action: str, *, before: dict | None = None,
           after: dict | None = None, rationale: str | None = None) -> None:
    # clock_timestamp(), not the default now(): one action writes several events in a transaction (accept, then
    # start of the next step) and now() would give them the same time and no order
    conn.execute(
        "insert into public.audit_event (entity_type, entity_id, actor, action, before, after, rationale, timestamp) "
        "values (%s, %s, %s, %s, %s, %s, %s, clock_timestamp())",
        (entity_type, entity_id, actor, action, Jsonb(before) if before is not None else None,
         Jsonb(after) if after is not None else None, rationale))


def _locked_run(conn, run_id: UUID) -> dict:
    run = conn.execute("select * from public.pipeline_run where id = %s for update", (run_id,)).fetchone()
    if not run:
        raise service.RunNotFound(str(run_id))
    return run


def _locked_step(conn, step_id: UUID) -> tuple[dict, dict]:
    """The step and its run, both locked. The run is locked first, the same order everywhere."""
    found = conn.execute("select run_id from public.step where id = %s", (step_id,)).fetchone()
    if not found:
        raise StepNotFound(str(step_id))
    run = _locked_run(conn, found["run_id"])
    step = conn.execute("select * from public.step where id = %s for update", (step_id,)).fetchone()
    if run["status"] != "in_progress":
        raise StepConflict(f"this run is {run['status']}")
    return step, run


def _transition(step: dict, action: StepAction) -> str:
    try:
        return next_status(StepStatus(step["status"]), action).value
    except InvalidTransition as e:
        raise StepConflict(str(e)) from None


def _output_of(step: dict) -> dict[str, Any] | None:
    stored = step.get("structured_output_refs")
    return stored.get("output") if isinstance(stored, dict) else None


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _with_finding_ids(output: dict[str, Any]) -> dict[str, Any]:
    """Later agents cite findings by id. A finding without one gets a stable id from its locator and text."""
    for finding in output.get("findings") or []:
        if isinstance(finding, dict) and not finding.get("id"):
            finding["id"] = str(uuid5(NAMESPACE_URL, f"{finding.get('locator')}|{finding.get('text')}"))
    return output


def _final_text(run: dict, steps: list[dict]) -> str:
    """The final result is compiled from accepted steps only; a failed step is named as a coverage gap."""
    accepted = [s for s in steps if s["status"] == "accepted"]
    gaps = [f"- {s['agent_name']} could not finish" + (f": {s['pm_note']}" if s.get("pm_note") else "")
            for s in steps if s["status"] == "rejected"]
    dossier = next(((_output_of(s) or {}).get("dossier") for s in reversed(accepted)
                    if s["agent_name"] == DOCUMENTATION_AGENT), None)
    if isinstance(dossier, str) and dossier.strip():
        return dossier
    if not accepted:
        return "No agent produced a usable result, so there is no research result.\n\nCoverage gaps:\n" + "\n".join(gaps)
    parts = [f"Research result: {run['query_text']}"]
    parts += [f"## {s['agent_name']}\n{s['human_readable_summary'] or ''}".rstrip() for s in accepted]
    if gaps:
        parts.append("## Coverage gaps\n" + "\n".join(gaps))
    return "\n\n".join(parts)


def _complete(conn, run: dict, steps: list[dict], messages: list[dict], answer: str | None = None) -> None:
    from .review import build_review

    conn.execute("update public.pipeline_run set status = 'completed' where id = %s", (run["id"],))
    accepted = [str(s["id"]) for s in steps if s["status"] == "accepted"]
    rejected = [s["agent_name"] for s in steps if s["status"] == "rejected"]
    filed = _register_requirements(conn, run["id"])
    review = build_review(run, steps)
    messages.append(service.add_message(
        conn, run["conversation_id"], "orchestrator", "final_result", answer or _final_text(run, steps), run_id=run["id"],
        payload={"accepted_step_ids": accepted, "coverage_gaps": rejected, "requirements": filed,
                 "dossier": any(s["agent_name"] == DOCUMENTATION_AGENT and s["status"] == "accepted" for s in steps),
                 "written_by": "orchestrator" if answer else "summaries",
                 **({"research_review": review} if review else {})}))
    _audit(conn, "pipeline_run", run["id"], "orchestrator", "run_completed",
           after={"accepted_steps": len(accepted), "coverage_gaps": rejected, "requirements": filed})


def _register_requirements(conn, run_id: UUID) -> int:
    """File the run's drafted requirements in the register for the PM to review. A failure here must never
    lose the research result, so it is contained in a savepoint and left in the log."""
    try:
        with conn.transaction():
            return register.sync_run(conn, run_id)
    except psycopg.Error:
        log.exception("could not file the requirements of run %s", run_id)
        return 0


# ---------------------------------------------------------------- running an agent

def _context(conn, run: dict, step: dict) -> StepContext:
    earlier = conn.execute("select * from public.step where run_id = %s and position < %s order by position",
                           (run["id"], step["position"])).fetchall()
    ids = [run["id"]] + [s["id"] for s in earlier]
    events = conn.execute("select entity_type, entity_id, actor, action, rationale, timestamp from public.audit_event "
                          "where entity_id = any(%s) order by timestamp, id", (ids,)).fetchall()
    steps = [{"id": str(s["id"]), "agent_name": s["agent_name"], "stage": s["stage"], "position": s["position"],
              "status": s["status"], "attempt": s["attempt"], "human_readable_summary": s["human_readable_summary"],
              "pm_note": s["pm_note"], "resolved_by": s["resolved_by"],
              "resolved_at": s["resolved_at"].isoformat() if s["resolved_at"] else None, "output": _output_of(s) or {}}
             for s in earlier]
    decisions = [{**e, "entity_id": str(e["entity_id"]), "timestamp": e["timestamp"].isoformat()} for e in events]
    return StepContext(query=run["query_text"] or "", vehicle_line=run["vehicle_line"], market=run["market"],
                       run_id=str(run["id"]), steps=steps, decisions=decisions,
                       comparison_context=run.get('comparison_context'))


def _failure_reason(error: BaseException) -> str:
    if isinstance(error, psycopg.Error):
        return f"database error ({type(error).__name__})"     # the message may name the host
    return f"{type(error).__name__}: {str(error)[:300]}".rstrip(": ")


def _critic_report(verdict: critic.CriticVerdict) -> dict[str, Any]:
    return _json_safe({
        "attempts": verdict.attempts, "retries_exhausted": verdict.retries_exhausted, "note": verdict.note,
        "downgrades": [asdict(d) for d in verdict.downgrades], "dropped": [asdict(d) for d in verdict.dropped],
        "warnings": [asdict(i) for i in verdict.issues if i.severity != "error"],
    })


def execute_step(conn, step_id: UUID, runners: dict[str, AgentRunner] | None = None,
                 max_retries: int = MAX_CRITIC_RETRIES) -> bool:
    """Run the agent of a `running` step behind the Critic and store the output. Returns True when the step was
    accepted, False when the agent failed (the step is then rejected, with the reason on it and no output).

    Commits its own work: it runs outside a request. A failing agent never hangs the run: its card says what
    happened and the orchestrator decides what to do without it.
    """
    runners = RUNNERS if runners is None else runners
    step = conn.execute("select * from public.step where id = %s", (step_id,)).fetchone()
    if not step or step["status"] != "running":
        return False
    run = conn.execute("select * from public.pipeline_run where id = %s", (step["run_id"],)).fetchone()
    ctx = _context(conn, run, step)
    conn.commit()                       # no open transaction while the agent works

    output: dict[str, Any] | None = None
    report: dict[str, Any] = {}
    events: list[dict[str, Any]] = []
    try:
        runner = runners[step["agent_name"]]
        verdict = critic.review_with_retries(lambda instruction: runner(replace(ctx, instruction=instruction)),
                                             max_retries=max_retries, known_findings=ctx.accepted("findings"))
        output = _with_finding_ids(_json_safe(verdict.output))
        report, events = _critic_report(verdict), critic.audit_events(verdict)
        summary = str(output.get("summary") or f"{step['agent_name']} produced no summary.")
    except (Exception, SystemExit) as error:    # agent modules raise SystemExit for a missing dependency or key
        reason = _failure_reason(error)
        summary = f"{step['agent_name']} could not finish: {reason}.\n\nNothing was produced."

    step, run = _locked_step(conn, step_id)
    ok = output is not None
    conn.execute("update public.step set status = %s, human_readable_summary = %s, structured_output_refs = %s, "
                 "resolved_by = 'orchestrator', resolved_at = now(), pm_note = %s where id = %s",
                 (_transition(step, StepAction.FINISH if ok else StepAction.FAIL), summary,
                  Jsonb({"output": output, "critic": report}), None if ok else summary.split("\n")[0], step_id))
    service.add_message(conn, run["conversation_id"], "agent", "step_card", summary, run_id=run["id"], step_id=step_id,
                        payload={"agent": step["agent_name"], "attempt": step["attempt"], "failed": not ok,
                                 "critic": report, "output": output})
    _audit(conn, "step", step_id, step["agent_name"], "step_finished" if ok else "step_failed",
           after={"attempt": step["attempt"], "findings": len((output or {}).get("findings") or []),
                  "critic_attempts": report.get("attempts")},
           rationale=None if ok else summary.split("\n")[0])
    for event in events:                # the Critic's downgrades and drops, filed under the step
        _audit(conn, "step", step_id, event["actor"], event["action"], before=_json_safe(event.get("before")),
               after={**_json_safe(event.get("after") or {}), "item": str(event.get("entity_id"))},
               rationale=event.get("rationale"))
    conn.commit()
    return ok
