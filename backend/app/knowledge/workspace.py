"""Database-backed PM workspace. Missing business values stay missing; no fixture fallbacks."""
from __future__ import annotations

from uuid import UUID

from psycopg.types.json import Jsonb


class UnknownScope(ValueError):
    pass


class RequirementNotFound(LookupError):
    pass


class ReviewConflict(ValueError):
    pass


TRANSITIONS = {
    "draft": ("pm_review", "rejected"),
    "proposed": ("pm_review", "rejected"),
    "pm_review": ("tracked", "rejected"),
    "tracked": ("challenged", "superseded"),
    "challenged": ("pm_review", "rejected"),
    "rejected": (),
    "superseded": (),
}


def config(conn) -> dict:
    rows = conn.execute("select kind, key, label from public.ontology where active order by label, key").fetchall()
    return {name: [{"key": r["key"], "label": r["label"]} for r in rows if r["kind"] == kind]
            for name, kind in (("lines", "vehicle_line"), ("markets", "market"))}


def validate_scope(conn, line: str | None, market: str | None) -> None:
    for kind, key in (("vehicle_line", line), ("market", market)):
        if key is not None and not conn.execute(
            "select 1 from public.ontology where kind = %s and key = %s and active", (kind, key)
        ).fetchone():
            raise UnknownScope(f"unknown {kind}")


def snapshot(conn, line: str | None = None, market: str | None = None) -> dict:
    validate_scope(conn, line, market)
    params = {"line": line, "market": market}
    raw_scope = "(%(line)s::text is null or vehicle_line = %(line)s) and (%(market)s::text is null or market_code = %(market)s)"
    run_scope = "(%(line)s::text is null or p.vehicle_line in (%(line)s, 'ALL')) and (%(market)s::text is null or p.market in (%(market)s, 'ALL'))"
    req_scope = "(%(line)s::text is null or r.vehicle_line in (%(line)s, 'ALL')) and (%(market)s::text is null or cardinality(r.markets) = 0 or %(market)s = any(r.markets) or 'ALL' = any(r.markets))"
    counts = {
        "feedback": conn.execute(f"select count(*) as n from public.feedback_raw where {raw_scope}", params).fetchone()["n"],
        "study_cells": conn.execute(f"select count(*) as n from public.study_response where {raw_scope}", params).fetchone()["n"],
        "catalog_options": conn.execute("select count(*) as n from public.option where (%(line)s::text is null or vehicle_line = %(line)s)", params).fetchone()["n"],
        "pending_steps": conn.execute(f"select count(*) as n from public.step s join public.pipeline_run p on p.id = s.run_id where s.status = 'awaiting_review' and p.status = 'in_progress' and {run_scope}", params).fetchone()["n"],
    }
    requirements = conn.execute(
        "select r.id, r.code, r.title, r.description, r.vehicle_line, r.markets, r.status, r.metric, "
        "r.acceptance_criteria, r.evidence_level, r.assumptions, r.uncertainties, r.created_at, "
        "o.label as domain, sc.composite as score, sc.confidence, sc.rationale as score_rationale, "
        "sc.weight_vector_version, sc.computed_at as scored_at "
        "from public.requirement r left join public.ontology o on o.id = r.ontology_domain_id "
        "left join lateral (select * from public.score where requirement_id = r.id order by computed_at desc, id desc limit 1) sc on true "
        f"where {req_scope} order by r.created_at desc, r.id", params).fetchall()
    for req in requirements:
        req["allowed_statuses"] = list(TRANSITIONS.get(req["status"], ()))
        req["citations"] = conn.execute(
            "select f.id, s.uri as file, f.locator, coalesce(to_jsonb(f)->>'source_snapshot', f.text) as quote, f.evidence_level "
            "from public.requirement_finding rf join public.finding f on f.id = rf.finding_id "
            "join public.source s on s.id = f.source_id where rf.requirement_id = %s order by s.uri, f.locator, f.id",
            (req["id"],)).fetchall()
    sales = conn.execute(
        "select v.id, v.vehicle_line, v.market_code, v.year, v.volume, v.is_forecast, e.file, e.locator "
        "from public.sales_volume v join public.evidence_item e on e.kind = 'sales' and e.id = v.id "
        f"where {raw_scope.replace('vehicle_line', 'v.vehicle_line').replace('market_code', 'v.market_code')} "
        "order by v.year, v.vehicle_line, v.market_code, v.id", params).fetchall()
    options = conn.execute(
        "select o.id, o.vehicle_line, o.code, o.name, o.description, e.file, e.locator, "
        "(select count(*) from public.option_availability a where a.option_id = o.id and a.status = 'standard') as standard_variants, "
        "(select count(*) from public.option_availability a where a.option_id = o.id and a.status = 'optional') as optional_variants "
        "from public.option o join public.evidence_item e on e.kind = 'option' and e.id = o.id "
        "where (%(line)s::text is null or o.vehicle_line = %(line)s) order by o.vehicle_line, o.code, o.id limit 25", params).fetchall()
    studies = conn.execute(
        "select r.id, r.vehicle_line, r.market_code, r.model, r.question, r.metric, r.answer_option, r.value, e.file, e.locator "
        "from public.study_response r join public.evidence_item e on e.kind = 'study' and e.id = r.id "
        f"where {raw_scope.replace('vehicle_line', 'r.vehicle_line').replace('market_code', 'r.market_code')} "
        "order by r.question, r.model, r.metric, r.answer_option, r.id limit 20", params).fetchall()
    runs = conn.execute(
        "select p.id, p.conversation_id, p.query_text, p.vehicle_line, p.market, p.status, p.created_at, "
        "(select count(*) from public.step s where s.run_id = p.id and s.status = 'awaiting_review') as awaiting_review "
        f"from public.pipeline_run p where {run_scope} order by p.created_at desc, p.id limit 50", params).fetchall()
    results = conn.execute(
        "select s.id, s.agent_name, s.human_readable_summary as summary, s.structured_output_refs->'output' as output, "
        "s.resolved_at, s.resolved_by, p.id as run_id, p.conversation_id, p.status as run_status, p.vehicle_line, p.market "
        "from public.step s join public.pipeline_run p on p.id = s.run_id "
        "where s.status = 'accepted' and jsonb_typeof(s.structured_output_refs->'output') = 'object' "
        f"and {run_scope} order by s.resolved_at desc, s.id limit 100", params).fetchall()
    audits = conn.execute(
        "select a.id, a.entity_type, a.entity_id, a.action, a.actor, a.rationale, a.timestamp, a.before, a.after "
        "from public.audit_event a left join public.step s on a.entity_type = 'step' and s.id = a.entity_id "
        "left join public.pipeline_run p on p.id = case when a.entity_type = 'pipeline_run' then a.entity_id else s.run_id end "
        "left join public.requirement r on a.entity_type = 'requirement' and r.id = a.entity_id "
        f"where (p.id is not null and {run_scope}) or (r.id is not null and {req_scope}) "
        "order by a.timestamp desc, a.id limit 100", params).fetchall()
    return {"generated_at": conn.execute("select clock_timestamp() as time").fetchone()["time"],
            "counts": counts, "requirements": requirements, "sales": sales, "options": options,
            "studies": studies, "runs": runs, "results": results, "audits": audits}


def review_requirement(conn, requirement_id: UUID, status: str, expected_status: str, reason: str, actor: str) -> dict:
    current = conn.execute("select id, status from public.requirement where id = %s for update", (requirement_id,)).fetchone()
    if current is None:
        raise RequirementNotFound()
    if current["status"] != expected_status:
        raise ReviewConflict("the requirement changed; refresh it before reviewing")
    if status not in TRANSITIONS.get(current["status"], ()):
        raise ReviewConflict("this status change is not allowed")
    if len(reason.strip()) < 3:
        raise ReviewConflict("a review reason of at least three characters is required")
    conn.execute("update public.requirement set status = %s where id = %s", (status, requirement_id))
    conn.execute(
        "insert into public.audit_event (entity_type, entity_id, actor, action, before, after, rationale) "
        "values ('requirement', %s, %s, 'requirement_status_changed', %s, %s, %s)",
        (requirement_id, actor, Jsonb({"status": current["status"]}), Jsonb({"status": status}), reason.strip()))
    return {"id": requirement_id, "status": status}
