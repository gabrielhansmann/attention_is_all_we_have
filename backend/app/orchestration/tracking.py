"""The tracking loop (stage "Requirements tracking" in BMW's process slide, docs/architecture/05).

A check re-reads the customer evidence for every tracked requirement and hands it to the Delta / Tracking Agent,
which flags `new_evidence`, `contradicting` and `stale` for the PM. The agent only flags: a requirement's status
changes only when the PM decides. Flags are audit events on the requirement; a flag stays open until the PM
acknowledges the requirement.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from app.agents import delta_tracking_agent as delta

from . import register

SEARCH_K = 12
POLARITY_SIGNAL = {"negative": "complaint", "positive": "praise", "request": "unmet_need"}

Search = Callable[..., list[Any]]


def _finding_of(hit: Any) -> dict[str, Any]:
    c, meta = hit.citation, hit.meta or {}
    return {"id": c.id, "text": hit.text, "source": c.file, "locator": c.locator, "kind": c.kind,
            "signal_type": POLARITY_SIGNAL.get(meta.get("polarity")), "vehicle_line": meta.get("vehicle_line"),
            "market": meta.get("market_code"), "citations": [asdict(c)]}


def _search(query: str, **kw: Any) -> list[Any]:
    from app.knowledge import tools
    return tools.search_feedback(query, **kw)


def _evidence_of(conn, row: dict) -> list[dict[str, Any]]:
    """The findings the requirement was drafted from, read back from its run."""
    wanted = {str(i) for i in (row["payload"] or {}).get("linked_finding_ids") or []}
    if not wanted or not row.get("run_id"):
        return []
    return [f for f in register.run_findings(conn, row["run_id"]) if str(f.get("id")) in wanted]


def _requirement_for_agent(row: dict) -> dict[str, Any]:
    p = row["payload"] or {}
    return {"id": str(row["id"]), "code": row["code"], "status": row["status"], "title": row["title"],
            "description": (p.get("description") or {}).get("text", ""), "vehicle_line": row["vehicle_line"],
            "markets": p.get("markets") or []}


def check(conn, actor: str = "tracking", requirement_ids: list[UUID] | None = None,
          search: Search | None = None) -> dict[str, Any]:
    """Check tracked requirements (all, or the given ones) for changed evidence and file the flags.
    The caller commits. Returns the agent's summary and the flags."""
    search = search or _search
    rows = [r for r in register.list_requirements(conn, status="tracked")
            if requirement_ids is None or r["id"] in set(requirement_ids)]
    requirements, existing, fresh, errors = [], [], {}, []
    for row in rows:
        evidence = _evidence_of(conn, row)
        requirements.append({**_requirement_for_agent(row), "evidence": evidence})
        existing += evidence
        line = row["vehicle_line"] if row["vehicle_line"] not in ("ALL", "") else None
        try:
            for hit in search(row["title"], line=line, k=SEARCH_K):
                fresh.setdefault(hit.citation.id, _finding_of(hit))
        except Exception as e:           # one failed search must not hide the others
            errors.append(f"{row['code']}: evidence search failed ({type(e).__name__})")
    result = delta.build_result("ALL", "ALL", requirements, list(fresh.values()), existing_findings=existing,
                                batch_id="tracking-check")
    for f in result.flags:
        conn.execute(
            "insert into public.audit_event (entity_type, entity_id, actor, action, after, rationale, timestamp) "
            "values ('requirement', %s, %s, %s, %s, %s, clock_timestamp())",
            (f.requirement_id, delta.AGENT_NAME, f"flagged_{f.flag_type}", Jsonb(asdict(f)), f.reason))
    for row in rows:
        conn.execute("insert into public.audit_event (entity_type, entity_id, actor, action, after, timestamp) "
                     "values ('requirement', %s, %s, 'tracking_checked', %s, clock_timestamp())",
                     (row["id"], actor, Jsonb({"flags": sum(1 for f in result.flags if f.requirement_id == str(row["id"]))})))
    return {"checked": result.requirements_checked, "summary": result.summary,
            "flags": [asdict(f) for f in result.flags], "skipped": result.skipped, "errors": errors}


def open_flags(conn) -> dict[UUID, list[dict]]:
    """Flags raised since the PM last acknowledged each tracked requirement, newest first."""
    rows = conn.execute(
        "select e.entity_id, e.action, e.after, e.rationale, e.timestamp from public.audit_event e "
        "join public.requirement_register r on r.id = e.entity_id "
        "where e.entity_type = 'requirement' and r.status = 'tracked' and e.action like 'flagged\\_%' "
        "and e.timestamp > coalesce((select max(a.timestamp) from public.audit_event a where a.entity_id = e.entity_id "
        "and a.entity_type = 'requirement' and a.action in ('acknowledge','approve')), '-infinity') "
        "order by e.timestamp desc").fetchall()
    out: dict[UUID, list[dict]] = {}
    for r in rows:
        out.setdefault(r["entity_id"], []).append({"flag_type": r["action"].removeprefix("flagged_"),
                                                   "reason": r["rationale"], "detected_at": r["timestamp"],
                                                   "citations": (r["after"] or {}).get("citations") or []})
    return out


def last_checked(conn) -> Any:
    row = conn.execute("select max(timestamp) as t from public.audit_event where entity_type = 'requirement' "
                       "and action = 'tracking_checked'").fetchone()
    return row["t"]
