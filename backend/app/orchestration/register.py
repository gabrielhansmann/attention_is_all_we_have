"""The requirement register: requirements a run produced and what the PM decided about each (decision 0022,
docs/architecture/05-requirement-lifecycle.md).

`sync_run` copies the accepted Requirements Drafting and Prioritization output of a finished run into
`requirement_register`. After that the PM moves each requirement through the lifecycle with `decide`; every
decision is an audit event on the requirement with the person and the reason. Nothing here calls a model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

DRAFTING, PRIORITIZATION, DOCUMENTATION = "Requirements Drafting Agent", "Prioritization Agent", "Documentation Agent"

STATUSES = ("draft", "pm_review", "tracked", "rejected", "challenged", "superseded")


class RequirementNotFound(LookupError):
    pass


class InvalidDecision(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    to: str | None              # None: the status does not change
    allowed_from: tuple[str, ...]
    note_required: bool


# The four verbs of docs/architecture/05 plus supersede, reopen and acknowledge (clear a tracking flag).
ACTIONS: dict[str, Action] = {
    "approve": Action("tracked", ("draft", "pm_review", "challenged"), False),
    "reject": Action("rejected", ("draft", "pm_review", "challenged"), True),
    "challenge": Action("challenged", ("draft", "pm_review", "tracked"), True),
    "supersede": Action("superseded", ("tracked",), True),
    "reopen": Action("draft", ("rejected", "challenged", "superseded"), False),
    "acknowledge": Action(None, ("tracked",), False),
}


def actions_for(status: str) -> list[str]:
    """The decisions a requirement in this status accepts, in the order the UI offers them."""
    return [name for name, a in ACTIONS.items() if status in a.allowed_from]


def _outputs(conn, run_id: UUID) -> dict[str, dict[str, Any]]:
    """The output of the last accepted step of each agent in a run."""
    out: dict[str, dict[str, Any]] = {}
    for step in conn.execute("select agent_name, structured_output_refs from public.step "
                             "where run_id = %s and status = 'accepted' order by position", (run_id,)).fetchall():
        stored = step["structured_output_refs"]
        if isinstance(stored, dict) and isinstance(stored.get("output"), dict):
            out[step["agent_name"]] = stored["output"]
    return out


def sync_run(conn, run_id: UUID) -> int:
    """Copy the run's drafted requirements (with their scores) into the register. A requirement the PM has
    already decided on keeps its status and text; a draft is refreshed. Returns the number of requirements seen."""
    run = conn.execute("select * from public.pipeline_run where id = %s", (run_id,)).fetchone()
    if not run:
        return 0
    outputs = _outputs(conn, run_id)
    requirements = [r for r in (outputs.get(DRAFTING) or {}).get("requirements") or [] if isinstance(r, dict) and r.get("id")]
    scores = {str(s.get("requirement_id")): s for s in (outputs.get(PRIORITIZATION) or {}).get("scores") or []
              if isinstance(s, dict)}
    for req in requirements:
        conn.execute(
            "insert into public.requirement_register (id, run_id, conversation_id, vehicle_line, market, title, payload, score) "
            "values (%s,%s,%s,%s,%s,%s,%s,%s) "
            "on conflict (id) do update set run_id = excluded.run_id, title = excluded.title, payload = excluded.payload, "
            "score = excluded.score, updated_at = now() where public.requirement_register.status in ('draft','challenged')",
            (req["id"], run_id, run.get("conversation_id"), req.get("vehicle_line") or run["vehicle_line"], run["market"],
             str(req.get("title") or "Untitled requirement")[:300], Jsonb(req), Jsonb(scores.get(str(req["id"])))))
    return len(requirements)


_LIST_COLUMNS = ("id, code, run_id, conversation_id, vehicle_line, market, title, status, payload, score, decided_by, "
                 "decided_at, decision_note, tracked_at, created_at, updated_at")


def list_requirements(conn, *, status: str | None = None, line: str | None = None, run_id: UUID | None = None,
                      conversation_id: UUID | None = None) -> list[dict]:
    rows = conn.execute(
        f"select {_LIST_COLUMNS} from public.requirement_register "
        "where (%(status)s::text is null or status = %(status)s) and (%(line)s::text is null or vehicle_line = %(line)s) "
        "and (%(run)s::uuid is null or run_id = %(run)s) and (%(conv)s::uuid is null or conversation_id = %(conv)s) "
        "order by coalesce((score->>'composite')::numeric, -1) desc, created_at desc",
        {"status": status, "line": line, "run": run_id, "conv": conversation_id}).fetchall()
    for r in rows:
        r["actions"] = actions_for(r["status"])
    return rows


def get_requirement(conn, requirement_id: UUID) -> dict:
    row = conn.execute(f"select {_LIST_COLUMNS} from public.requirement_register where id = %s", (requirement_id,)).fetchone()
    if not row:
        raise RequirementNotFound(str(requirement_id))
    row["actions"] = actions_for(row["status"])
    row["history"] = history(conn, requirement_id)
    return row


def history(conn, requirement_id: UUID) -> list[dict]:
    """The requirement's audit events, newest first: the PM's decisions and the tracking agent's flags."""
    return conn.execute(
        "select id, actor, action, before, after, rationale, timestamp from public.audit_event "
        "where entity_type = 'requirement' and entity_id = %s order by timestamp desc, id", (requirement_id,)).fetchall()


def decide(conn, requirement_id: UUID, action: str, actor: str, note: str | None = None) -> dict:
    """Apply one PM decision. The caller commits."""
    spec = ACTIONS.get(action)
    if spec is None:
        raise InvalidDecision(f"unknown decision: {action}")
    row = conn.execute("select status from public.requirement_register where id = %s for update", (requirement_id,)).fetchone()
    if not row:
        raise RequirementNotFound(str(requirement_id))
    note = (note or "").strip() or None
    if row["status"] not in spec.allowed_from:
        raise InvalidDecision(f"a {row['status']} requirement cannot be {action}d")
    if spec.note_required and not note:
        raise InvalidDecision(f"say why: a reason is required to {action} a requirement")
    new_status = spec.to or row["status"]
    conn.execute(
        "update public.requirement_register set status = %s, decided_by = %s, decided_at = now(), decision_note = %s, "
        "tracked_at = case when %s = 'tracked' and status <> 'tracked' then now() else tracked_at end, "
        "updated_at = now() where id = %s",
        (new_status, actor, note, new_status, requirement_id))
    conn.execute(
        "insert into public.audit_event (entity_type, entity_id, actor, action, before, after, rationale, timestamp) "
        "values ('requirement', %s, %s, %s, %s, %s, %s, clock_timestamp())",
        (requirement_id, actor, action, Jsonb({"status": row["status"]}), Jsonb({"status": new_status}), note))
    return get_requirement(conn, requirement_id)


def counts(conn) -> dict[str, int]:
    rows = conn.execute("select status, count(*) as n from public.requirement_register group by status").fetchall()
    return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------- dossiers

def list_dossiers(conn, limit: int = 30) -> list[dict]:
    """Completed Documentation steps, newest first, each with its run's request and scope."""
    rows = conn.execute(
        "select s.id as step_id, s.run_id, s.resolved_at, s.structured_output_refs, r.query_text, r.vehicle_line, "
        "r.market, r.conversation_id from public.step s join public.pipeline_run r on r.id = s.run_id "
        "where s.agent_name = %s and s.status = 'accepted' order by s.resolved_at desc nulls last limit %s",
        (DOCUMENTATION, limit)).fetchall()
    out = []
    for r in rows:
        output = (r["structured_output_refs"] or {}).get("output") if isinstance(r["structured_output_refs"], dict) else None
        text = (output or {}).get("dossier")
        if isinstance(text, str) and text.strip():
            out.append({"run_id": r["run_id"], "conversation_id": r["conversation_id"], "title": r["query_text"] or "Dossier",
                        "vehicle_line": r["vehicle_line"], "market": r["market"], "created_at": r["resolved_at"],
                        "dossier": text})
    return out


def run_findings(conn, run_id: UUID) -> list[dict]:
    """Every finding of a run's accepted steps, so a dossier's [finding-id] markers can be opened as citations."""
    found: list[dict] = []
    for output in _outputs_all(conn, run_id):
        found += [f for f in output.get("findings") or [] if isinstance(f, dict)]
    return json.loads(json.dumps(found, default=str))


def _outputs_all(conn, run_id: UUID) -> list[dict[str, Any]]:
    rows = conn.execute("select structured_output_refs from public.step where run_id = %s and status = 'accepted' "
                        "order by position", (run_id,)).fetchall()
    return [s["structured_output_refs"]["output"] for s in rows
            if isinstance(s["structured_output_refs"], dict) and isinstance(s["structured_output_refs"].get("output"), dict)]
