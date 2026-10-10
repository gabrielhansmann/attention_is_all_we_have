"""Step runner: starts planned steps, runs the agent behind the Critic, and applies the PM's four actions
(docs/architecture/02, decision 0015).

The transition rules live in `steps.py`; this module is the I/O around them. Like `service.py`, the PM-action
functions take an open connection and do NOT commit. They return `start_step_id` when a step was set to
`running`; the caller commits and then calls `execute_step` for it outside the request (it can take minutes).

A step's output is kept as JSON on the step (`structured_output_refs`), after the Critic's adjustments. Later
steps read the accepted output from there, so nothing an unaccepted step produced can reach them.
"""
from __future__ import annotations

import json
from dataclasses import asdict, replace
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from app.agents import critic_agent as critic

from . import service
from .agents import RUNNERS, AgentRunner, StepContext
from .catalog import get as agent_spec
from .steps import InvalidTransition, StepAction, StepStatus, next_status, next_to_start

MAX_CRITIC_RETRIES = 1        # each automatic retry re-runs the agent (model and web calls), so keep it small
DOCUMENTATION_AGENT = "Documentation Agent"


class StepNotFound(LookupError):
    pass


class StepConflict(ValueError):
    """The action is not allowed in the step's or the run's current state."""


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


def _transition(step: dict, action: StepAction, note: str | None = None) -> str:
    try:
        return next_status(StepStatus(step["status"]), action, note=note).value
    except InvalidTransition as e:
        raise StepConflict(str(e)) from None


def _result(conn, run: dict, messages: list[dict], start_step_id: UUID | None = None) -> dict:
    run = conn.execute("select * from public.pipeline_run where id = %s", (run["id"],)).fetchone()
    run["steps"] = service.list_steps(conn, run["id"])
    return {"messages": messages, "run": run, "start_step_id": start_step_id}


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


# ---------------------------------------------------------------- starting and finishing a run

def _start_next(conn, run: dict, messages: list[dict], reason: str) -> UUID | None:
    """Set the next planned step to `running`, or finish the run when none is left."""
    steps = service.list_steps(conn, run["id"])
    index = next_to_start([StepStatus(s["status"]) for s in steps])
    if index is None:
        if not any(s["status"] in ("running", "awaiting_review") for s in steps):
            _complete(conn, run, steps, messages)
        return None
    step = steps[index]
    if not step["available"]:
        messages.append(service.add_message(
            conn, run["conversation_id"], "orchestrator", "system_note",
            f"{step['agent_name']} is not built yet, so the run stops here. Reject the run or wait for the agent.",
            run_id=run["id"]))
        return None
    conn.execute("update public.step set status = %s, launched_by = 'orchestrator', launched_at = now() where id = %s",
                 (_transition(step, StepAction.START), step["id"]))
    _audit(conn, "step", step["id"], "orchestrator", "step_started",
           after={"agent": step["agent_name"], "position": step["position"]}, rationale=reason)
    return step["id"]


def _final_text(run: dict, steps: list[dict]) -> str:
    """The final result is compiled from accepted steps only; a rejected step is named as a coverage gap."""
    accepted = [s for s in steps if s["status"] == "accepted"]
    gaps = [f"- {s['agent_name']} was rejected" + (f": {s['pm_note']}" if s.get("pm_note") else "")
            for s in steps if s["status"] == "rejected"]
    dossier = next(((_output_of(s) or {}).get("dossier") for s in reversed(accepted)
                    if s["agent_name"] == DOCUMENTATION_AGENT), None)
    if isinstance(dossier, str) and dossier.strip():
        return dossier
    if not accepted:
        return "No agent output was accepted, so there is no research result.\n\nCoverage gaps:\n" + "\n".join(gaps)
    parts = [f"Research result: {run['query_text']}"]
    parts += [f"## {s['agent_name']}\n{s['human_readable_summary'] or ''}".rstrip() for s in accepted]
    if gaps:
        parts.append("## Coverage gaps\n" + "\n".join(gaps))
    return "\n\n".join(parts)


def _complete(conn, run: dict, steps: list[dict], messages: list[dict]) -> None:
    conn.execute("update public.pipeline_run set status = 'completed' where id = %s", (run["id"],))
    accepted = [str(s["id"]) for s in steps if s["status"] == "accepted"]
    rejected = [s["agent_name"] for s in steps if s["status"] == "rejected"]
    messages.append(service.add_message(
        conn, run["conversation_id"], "orchestrator", "final_result", _final_text(run, steps), run_id=run["id"],
        payload={"accepted_step_ids": accepted, "coverage_gaps": rejected}))
    _audit(conn, "pipeline_run", run["id"], "orchestrator", "run_completed",
           after={"accepted_steps": len(accepted), "coverage_gaps": rejected})


def start_run(conn, run_id: UUID) -> dict:
    """The PM confirms the plan: the first agent starts. After this the plan can no longer be edited."""
    run = _locked_run(conn, run_id)
    if run["status"] != "in_progress":
        raise StepConflict(f"this run is {run['status']}")
    if any(s["status"] != "planned" for s in service.list_steps(conn, run_id)):
        raise StepConflict("this run has already started")
    messages: list[dict] = []
    started = _start_next(conn, run, messages, "Plan confirmed by the PM")
    return _result(conn, run, messages, started)


# ---------------------------------------------------------------- the PM's four actions

def accept(conn, step_id: UUID, note: str | None = None) -> dict:
    """Accept is the only trigger for the next agent."""
    step, run = _locked_step(conn, step_id)
    conn.execute("update public.step set status = %s, resolved_by = 'pm', resolved_at = now() where id = %s",
                 (_transition(step, StepAction.ACCEPT), step_id))
    _audit(conn, "step", step_id, "pm", "step_accepted", after={"agent": step["agent_name"], "attempt": step["attempt"]},
           rationale=note)
    messages: list[dict] = []
    started = _start_next(conn, run, messages, f"{step['agent_name']} accepted by the PM")
    return _result(conn, run, messages, started)


def retry(conn, step_id: UUID, note: str) -> dict:
    """Same agent, same step, with the PM's steering note appended to its task."""
    step, run = _locked_step(conn, step_id)
    status = _transition(step, StepAction.RETRY, note)
    note = note.strip()
    conn.execute("update public.step set status = %s, attempt = attempt + 1, pm_note = %s, launched_by = 'pm', "
                 "launched_at = now() where id = %s", (status, note, step_id))
    message = service.add_message(conn, run["conversation_id"], "pm", "pushback", note, run_id=run["id"],
                                  step_id=step_id, payload={"action": "retry", "attempt": step["attempt"] + 1})
    _audit(conn, "step", step_id, "pm", "step_retried", before={"attempt": step["attempt"]},
           after={"attempt": step["attempt"] + 1}, rationale=note)
    return _result(conn, run, [message], step_id)


def reject(conn, step_id: UUID, note: str, proceed: bool) -> dict:
    """Reject, then either go on without this agent (a coverage gap downstream) or abort the run."""
    step, run = _locked_step(conn, step_id)
    note = note.strip()
    conn.execute("update public.step set status = %s, pm_note = %s, resolved_by = 'pm', resolved_at = now() "
                 "where id = %s", (_transition(step, StepAction.REJECT), note, step_id))
    messages = [service.add_message(conn, run["conversation_id"], "pm", "pushback", note, run_id=run["id"],
                                    step_id=step_id, payload={"action": "reject", "proceed": proceed})]
    _audit(conn, "step", step_id, "pm", "step_rejected", after={"agent": step["agent_name"], "proceed": proceed},
           rationale=note)
    if not proceed:
        conn.execute("update public.pipeline_run set status = 'aborted' where id = %s", (run["id"],))
        messages.append(service.add_message(
            conn, run["conversation_id"], "orchestrator", "system_note",
            f"Run aborted after {step['agent_name']} was rejected. No result is shown.", run_id=run["id"]))
        _audit(conn, "pipeline_run", run["id"], "pm", "run_aborted", rationale=note)
        return _result(conn, run, messages)
    messages.append(service.add_message(
        conn, run["conversation_id"], "orchestrator", "system_note",
        f"Proceeding without {step['agent_name']}. Everything downstream carries this as a coverage gap.",
        run_id=run["id"]))
    started = _start_next(conn, run, messages, f"{step['agent_name']} rejected by the PM, run continues")
    return _result(conn, run, messages, started)


def edit(conn, step_id: UUID, summary: str, note: str | None = None) -> dict:
    """The PM rewrites the step's summary before accepting. The diff is the audit event."""
    step, run = _locked_step(conn, step_id)
    _transition(step, StepAction.EDIT)
    summary = summary.strip()
    stored = step["structured_output_refs"] if isinstance(step["structured_output_refs"], dict) else {}
    if isinstance(stored.get("output"), dict):
        stored["output"]["summary"] = summary
    conn.execute("update public.step set human_readable_summary = %s, structured_output_refs = %s where id = %s",
                 (summary, Jsonb(stored), step_id))
    message = service.add_message(conn, run["conversation_id"], "pm", "step_card", summary, run_id=run["id"],
                                  step_id=step_id, payload={"agent": step["agent_name"], "attempt": step["attempt"],
                                                            "edited_by": "pm"})
    _audit(conn, "step", step_id, "pm", "step_edited", before={"summary": step["human_readable_summary"]},
           after={"summary": summary}, rationale=note)
    return _result(conn, run, [message])


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
                       run_id=str(run["id"]), note=step["pm_note"], steps=steps, decisions=decisions)


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
                 max_retries: int = MAX_CRITIC_RETRIES) -> None:
    """Run the agent of a `running` step behind the Critic, store the output and put the step up for review.

    Commits its own work: it runs outside a request. An agent that fails still ends in `awaiting_review`, with a
    card that says so and no output, so the PM can retry or reject instead of the run hanging.
    """
    runners = RUNNERS if runners is None else runners
    step = conn.execute("select * from public.step where id = %s", (step_id,)).fetchone()
    if not step or step["status"] != "running":
        return
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
        summary = (f"{step['agent_name']} could not finish: {reason}.\n\nNothing was produced. "
                   "Retry with a steering note, or reject the step.")

    step, run = _locked_step(conn, step_id)
    conn.execute("update public.step set status = %s, human_readable_summary = %s, structured_output_refs = %s "
                 "where id = %s", (_transition(step, StepAction.FINISH), summary,
                                   Jsonb({"output": output, "critic": report}), step_id))
    service.add_message(conn, run["conversation_id"], "agent", "step_card", summary, run_id=run["id"], step_id=step_id,
                        payload={"agent": step["agent_name"], "attempt": step["attempt"], "failed": output is None,
                                 "critic": report, "output": output})
    _audit(conn, "step", step_id, step["agent_name"], "step_finished" if output is not None else "step_failed",
           after={"attempt": step["attempt"], "findings": len((output or {}).get("findings") or []),
                  "critic_attempts": report.get("attempts")},
           rationale=None if output is not None else summary.split("\n")[0])
    for event in events:                # the Critic's downgrades and drops, filed under the step
        _audit(conn, "step", step_id, event["actor"], event["action"], before=_json_safe(event.get("before")),
               after={**_json_safe(event.get("after") or {}), "item": str(event.get("entity_id"))},
               rationale=event.get("rationale"))
    conn.commit()
