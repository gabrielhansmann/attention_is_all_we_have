"""Requirements Drafting Agent (Synthesizer, stage 03).

The agent turns each accepted cluster into one draft requirement: description, metric and
acceptance criteria. The model proposes the wording and names the findings behind every
statement; code decides (decision 0012): a statement only survives if it cites findings that
are members of its cluster, and a cluster without supporting findings yields no requirement.
Requirements are produced at `Draft`; the agent never changes status, priority or scope.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, TYPE_CHECKING

from app.agents.clustering_agent import (
    DEFAULT_DOMAINS,
    ClusterFinding,
    as_dict,
    cite_text,
    ensure_step,
    normalize_findings,
    out_of_scope_reason,
    require_openai,
    require_psycopg,
    resolve_domain,
    shorten,
)

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

AGENT_NAME = "Requirements Drafting Agent"
STAGE = 3
DRAFTING_MODEL = os.getenv("DRAFTING_AGENT_MODEL", "gpt-4.1-mini")
MAX_PROMPT_CHARS = 600
STATUS_DRAFT = "Draft"  # lifecycle entry state (doc 05); stored as 'draft' in requirement.status
EVIDENCE_ORDER = ["Verified", "Interpreted", "Unverified"]  # strongest first
NO_METRIC = "No defensible metric could be tied to the cited findings; the PM needs to set one."
NO_CRITERIA = "No acceptance criterion could be tied to the cited findings; the PM needs to add them."
NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")


@dataclass
class DraftCluster:
    id: str
    label: str
    domain_key: str | None
    domain_label: str | None
    ontology_domain_id: str | None
    members: list[ClusterFinding]
    missing_finding_ids: list[str] = field(default_factory=list)


@dataclass
class Statement:
    text: str
    finding_ids: list[str]
    citations: list[dict[str, str]]


@dataclass
class DraftRequirement:
    id: str
    cluster_id: str
    cluster_label: str
    title: str
    description: Statement
    metric: Statement | None
    acceptance_criteria: list[Statement]
    status: str
    domain_key: str | None
    domain_label: str | None
    ontology_domain_id: str | None
    markets: list[str]
    vehicle_line: str
    evidence_level: str
    assumptions: list[str]
    uncertainties: list[str]
    linked_finding_ids: list[str]
    linked_cluster_ids: list[str]
    citations: list[dict[str, str]]


@dataclass
class DraftingResult:
    agent_name: str
    vehicle_line: str
    market: str
    clusters_read: int
    findings_read: int
    requirements: list[DraftRequirement]
    skipped: list[dict[str, str]]
    out_of_scope: list[dict[str, str]]
    dropped: list[dict[str, str]]
    summary: str


def coerce_cluster(item: Any, findings_by_id: dict[str, ClusterFinding]) -> DraftCluster:
    """A cluster with its linked findings, either embedded (`members`) or resolved from `findings_by_id`."""
    data = as_dict(item)
    embedded, _ = normalize_findings(list(data.get("members") or data.get("findings") or []))
    by_id = {f.id: f for f in embedded}
    member_ids = [str(v) for v in data.get("member_finding_ids") or data.get("finding_ids") or []] or list(by_id)
    members: list[ClusterFinding] = []
    missing: list[str] = []
    for finding_id in dict.fromkeys(member_ids):
        finding = by_id.get(finding_id) or findings_by_id.get(finding_id)
        if finding:
            members.append(finding)
        else:
            missing.append(finding_id)
    domain = resolve_domain(data.get("domain_key") or data.get("domain") or data.get("ontology_domain_id"), DEFAULT_DOMAINS)
    domain_key = data.get("domain_key") or (domain["key"] if domain else None)
    ontology_domain_id = data.get("ontology_domain_id")
    return DraftCluster(
        id=str(data.get("id") or ""),
        label=str(data.get("label") or "").strip(),
        domain_key=domain_key,
        domain_label=data.get("domain_label") or (domain.get("label") if domain else None),
        ontology_domain_id=str(ontology_domain_id) if ontology_domain_id else None,
        members=members,
        missing_finding_ids=missing,
    )


def load_clusters(path: Path) -> list[dict[str, Any]]:
    """A JSON list of clusters, or an object with a `clusters` list (the Clustering Agent's result)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("clusters")
    if not isinstance(payload, list):
        raise ValueError("Clusters JSON must be a list of objects or an object with a `clusters` list")
    return payload


def load_drafting_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Requirements Drafting Agent draft JSON must be an object")
    payload.setdefault("requirements", [])
    return payload


def build_drafting_prompt(vehicle_line: str, market: str, clusters: list[DraftCluster]) -> str:
    cluster_blocks = "\n\n".join(
        f"Cluster {c.id} | label: {c.label} | domain: {c.domain_label or 'unknown'}\n"
        + "\n".join(
            f"  [{f.id}] signal_type: {f.signal_type} | evidence: {f.evidence_level} | market: {f.market}\n"
            f"  {f.text[:MAX_PROMPT_CHARS]}"
            for f in c.members
        )
        for c in clusters
    )
    return f"""You are the Requirements Drafting Agent for a vehicle requirements pipeline.

Scope:
- vehicle_line: {vehicle_line}
- market: {market}

Task:
- Draft exactly one customer-facing requirement per cluster, from the customer's point of view.
- Use only what the cluster's findings say. Every statement must name the finding ids that support it.
- Give a measurable metric. If the findings give no defensible number, say so in the metric text
  instead of inventing one.
- Give acceptance criteria as short, checkable statements.
- List what you had to assume and what stays uncertain, separately from the evidence.
- Do not set status, priority, score or scope. Do not draft pricing, regulatory or engineering-internal content.
- Skip a cluster if its findings do not support a requirement.

Return strict JSON with this shape:
{{
  "requirements": [
    {{
      "cluster_id": "id of the cluster",
      "title": "short requirement title",
      "description": {{"text": "what the customer needs", "finding_ids": ["id"]}},
      "metric": {{"text": "measurable target", "finding_ids": ["id"]}},
      "acceptance_criteria": [{{"text": "checkable criterion", "finding_ids": ["id"]}}],
      "assumptions": ["what was assumed"],
      "uncertainties": ["what is thin or unknown"]
    }}
  ]
}}

Clusters:
{cluster_blocks}
"""


def prepare_clusters(clusters: list[Any], findings: list[Any] | None = None) -> list[DraftCluster]:
    extra, _ = normalize_findings(list(findings or []))
    findings_by_id = {f.id: f for f in extra}
    return [c if isinstance(c, DraftCluster) else coerce_cluster(c, findings_by_id) for c in clusters]


def draft_requirements_with_openai(
    client: "OpenAIClient", vehicle_line: str, market: str, clusters: list[Any], findings: list[Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Ask the model for wording. Out-of-scope findings and empty clusters are not shown to it.
    `note` is steering from the PM or the Critic on a retry, appended to the task."""
    prepared = []
    for cluster in prepare_clusters(clusters, findings):
        members = [m for m in cluster.members if not out_of_scope_reason(m, DEFAULT_DOMAINS)]
        if members:
            prepared.append(DraftCluster(cluster.id, cluster.label, cluster.domain_key, cluster.domain_label, cluster.ontology_domain_id, members))
    response = client.responses.create(
        model=DRAFTING_MODEL,
        input=build_drafting_prompt(vehicle_line, market, prepared) + (f"\n\nSteering for this run:\n{note}" if note else ""),
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)


def requirement_id_for(cluster_id: str) -> str:
    """Deterministic uuid per cluster, so a retry of the step replaces its draft instead of adding one."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "requirement|" + cluster_id))


def validate_statement(
    raw: Any, part: str, cluster: DraftCluster, supporting: dict[str, ClusterFinding], dropped: list[dict[str, str]]
) -> Statement | None:
    """Keep a statement only with the cluster findings it cites; anything else is dropped and reported."""
    if raw is None:
        return None
    data = raw if isinstance(raw, dict) else {"text": raw}
    text = " ".join(str(data.get("text") or "").split())
    if not text:
        return None
    finding_ids: list[str] = []
    for finding_id in dict.fromkeys(str(v) for v in data.get("finding_ids") or []):
        if finding_id in supporting:
            finding_ids.append(finding_id)
        else:
            reason = "cited finding is not an in-scope member of the cluster"
            dropped.append({"cluster_id": cluster.id, "part": part, "finding_id": finding_id, "reason": reason})
    if not finding_ids:
        dropped.append({"cluster_id": cluster.id, "part": part, "text": text, "reason": "statement cites no finding of the cluster"})
        return None
    citations = [supporting[i].ref for i in finding_ids]
    return Statement(text=text, finding_ids=finding_ids, citations=citations)


def weakest_evidence(findings: list[ClusterFinding]) -> str:
    """Overall evidence level of a requirement: the weakest level among its linked findings."""
    ranks = [EVIDENCE_ORDER.index(f.evidence_level) if f.evidence_level in EVIDENCE_ORDER else len(EVIDENCE_ORDER) - 1 for f in findings]
    return EVIDENCE_ORDER[max(ranks)]


def ids_text(findings: list[ClusterFinding]) -> str:
    return ", ".join(f.id for f in findings)


def derive_assumptions(linked: list[ClusterFinding]) -> list[str]:
    """Assumptions that follow from the character of the evidence, stated without a model."""
    assumptions: list[str] = []
    trend = [f for f in linked if f.signal_type == "market_trend"]
    if trend and len(trend) == len(linked):
        assumptions.append(
            f"Rests only on market-trend research, an assumption about the future rather than an observed fact ({ids_text(trend)})."
        )
    elif trend:
        assumptions.append(
            f"Partly rests on market-trend research, an assumption about the future rather than an observed fact ({ids_text(trend)})."
        )
    if len(linked) == 1:
        assumptions.append(f"Thin evidence: a single supporting finding ({linked[0].id}).")
    elif len({f.source_key for f in linked}) == 1:
        assumptions.append(f"Single source: all {len(linked)} supporting findings come from {linked[0].source_key}.")
    unverified = [f for f in linked if f.evidence_level not in ("Verified", "Interpreted")]
    if unverified:
        assumptions.append(f"Includes unverified evidence that needs corroboration ({ids_text(unverified)}).")
    for finding in linked:
        for assumption in finding.assumptions:
            assumptions.append(f"{assumption} (carried over from finding {finding.id})")
    return assumptions


def unseen_numbers(statements: list[Statement], supporting: dict[str, ClusterFinding]) -> list[str]:
    """Numbers in a statement that none of its cited findings contain: targets the model proposed."""
    unseen: list[str] = []
    for statement in statements:
        evidence = " ".join(supporting[i].text for i in statement.finding_ids)
        seen = set(NUMBER_RE.findall(evidence))
        unseen.extend(n for n in NUMBER_RE.findall(statement.text) if n not in seen and n not in unseen)
    return unseen


def build_result(
    vehicle_line: str, market: str, clusters: list[Any], draft: dict[str, Any], findings: list[Any] | None = None
) -> DraftingResult:
    prepared = prepare_clusters(clusters, findings)
    known_ids = {c.id for c in prepared}
    skipped: list[dict[str, str]] = []
    dropped: list[dict[str, str]] = []
    out_of_scope: list[dict[str, str]] = []
    requirements: list[DraftRequirement] = []

    proposals: dict[str, dict[str, Any]] = {}
    for item in draft.get("requirements") or []:
        cluster_id = str(item.get("cluster_id") or "")
        if cluster_id not in known_ids:
            dropped.append({"cluster_id": cluster_id, "part": "requirement", "reason": "draft referenced an unknown cluster id"})
        elif cluster_id in proposals:
            dropped.append({"cluster_id": cluster_id, "part": "requirement", "reason": "second draft for the same cluster; first one kept"})
        else:
            proposals[cluster_id] = item

    for cluster in prepared:
        supporting: dict[str, ClusterFinding] = {}
        for member in cluster.members:
            reason = out_of_scope_reason(member, DEFAULT_DOMAINS)
            if reason:
                out_of_scope.append(
                    {"cluster_id": cluster.id, **member.ref, "text": member.text, "reason": reason}
                )
            else:
                supporting[member.id] = member
        if not supporting:
            skipped.append({"cluster_id": cluster.id, "cluster": cluster.label, "reason": "cluster has no supporting in-scope findings"})
            continue
        proposal = proposals.get(cluster.id)
        if proposal is None:
            skipped.append({"cluster_id": cluster.id, "cluster": cluster.label, "reason": "no draft was proposed for this cluster"})
            continue

        description = validate_statement(proposal.get("description"), "description", cluster, supporting, dropped)
        if description is None:
            skipped.append({"cluster_id": cluster.id, "cluster": cluster.label, "reason": "description cites no finding of the cluster"})
            continue
        metric = validate_statement(proposal.get("metric"), "metric", cluster, supporting, dropped)
        criteria_raw = proposal.get("acceptance_criteria") or []
        if not isinstance(criteria_raw, list):
            criteria_raw = [criteria_raw]
        criteria = [
            s for s in (validate_statement(raw, "acceptance_criteria", cluster, supporting, dropped) for raw in criteria_raw) if s
        ]

        statements = [description, *([metric] if metric else []), *criteria]
        linked_ids = list(dict.fromkeys(i for s in statements for i in s.finding_ids))
        linked = [supporting[i] for i in linked_ids]

        assumptions = derive_assumptions(linked)
        proposed_numbers = unseen_numbers([*([metric] if metric else []), *criteria], supporting)
        if proposed_numbers:
            assumptions.append(
                f"Target value(s) {', '.join(proposed_numbers)} are proposed by the drafting model and do not appear in the cited findings."
            )
        assumptions.extend(f"Model assumption: {str(v).strip()}" for v in proposal.get("assumptions") or [] if str(v).strip())

        uncertainties: list[str] = []
        if metric is None:
            uncertainties.append(NO_METRIC)
        if not criteria:
            uncertainties.append(NO_CRITERIA)
        unused = [f for f in supporting.values() if f.id not in linked_ids]
        if unused:
            uncertainties.append(f"{len(unused)} cluster finding(s) are not used by any statement ({ids_text(unused)}).")
        if cluster.missing_finding_ids:
            uncertainties.append(
                f"Cluster member(s) without an accepted finding were ignored ({', '.join(cluster.missing_finding_ids)})."
            )
        uncertainties.extend(f"Model uncertainty: {str(v).strip()}" for v in proposal.get("uncertainties") or [] if str(v).strip())

        lines = sorted({f.vehicle_line for f in linked if f.vehicle_line})
        requirements.append(
            DraftRequirement(
                id=requirement_id_for(cluster.id),
                cluster_id=cluster.id,
                cluster_label=cluster.label,
                title=" ".join(str(proposal.get("title") or "").split()) or cluster.label,
                description=description,
                metric=metric,
                acceptance_criteria=criteria,
                status=STATUS_DRAFT,
                domain_key=cluster.domain_key,
                domain_label=cluster.domain_label,
                ontology_domain_id=cluster.ontology_domain_id,
                markets=sorted({f.market for f in linked if f.market}) or [market],
                vehicle_line=lines[0] if len(lines) == 1 else vehicle_line,
                evidence_level=weakest_evidence(linked),
                assumptions=list(dict.fromkeys(assumptions)),
                uncertainties=uncertainties,
                linked_finding_ids=linked_ids,
                linked_cluster_ids=[cluster.id],
                citations=[f.ref for f in linked],
            )
        )

    findings_read = len({m.id for c in prepared for m in c.members})
    summary = summarize(vehicle_line, market, len(prepared), findings_read, requirements, skipped, out_of_scope, dropped)
    return DraftingResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        clusters_read=len(prepared),
        findings_read=findings_read,
        requirements=requirements,
        skipped=skipped,
        out_of_scope=out_of_scope,
        dropped=dropped,
        summary=summary,
    )


def cited(statement: Statement) -> str:
    return "; ".join(f"{c['finding_id']}: {cite_text(c['source'], c['locator'])}" for c in statement.citations)


def summarize(
    vehicle_line: str,
    market: str,
    clusters_read: int,
    findings_read: int,
    requirements: list[DraftRequirement],
    skipped: list[dict[str, str]],
    out_of_scope: list[dict[str, str]],
    dropped: list[dict[str, str]],
) -> str:
    lines = [
        f"{AGENT_NAME} looked at {clusters_read} accepted cluster(s) with {findings_read} linked finding(s) for "
        f"{vehicle_line} / {market} and drafted {len(requirements)} requirement(s), each at status {STATUS_DRAFT}.",
        "",
        "Draft requirements:",
    ]
    if requirements:
        for req in requirements:
            lines.append(
                f"- {req.title} [{req.domain_label or 'no domain'}; evidence {req.evidence_level}; cluster: {req.cluster_label}]"
            )
            lines.append(f"  - Description: {req.description.text} ({cited(req.description)})")
            if req.metric:
                lines.append(f"  - Metric: {req.metric.text} ({cited(req.metric)})")
            else:
                lines.append(f"  - Metric: {NO_METRIC}")
            for criterion in req.acceptance_criteria:
                lines.append(f"  - Acceptance: {criterion.text} ({cited(criterion)})")
            for assumption in req.assumptions:
                lines.append(f"  - Assumption: {assumption}")
    else:
        lines.append("- No requirement could be drafted from the accepted clusters.")

    lines.extend(["", "Confidence and gaps:"])
    gaps: list[str] = []
    for req in requirements:
        gaps.extend(f"- {req.title}: {uncertainty}" for uncertainty in req.uncertainties)
    for item in skipped:
        gaps.append(f"- No requirement for cluster '{item['cluster']}': {item['reason']}.")
    if dropped:
        gaps.append(f"- {len(dropped)} proposed statement(s) or citation(s) were dropped by validation (see `dropped`).")
    if not requirements:
        gaps.append("- The step needs clusters with supporting findings or a steering note.")
    lines.extend(gaps or ["- Every statement cites at least one finding of its cluster; see the assumptions per requirement."])

    lines.extend(["", "Out of scope (routed to the side bin, not drafted):"])
    if out_of_scope:
        for item in out_of_scope:
            lines.append(f"- {shorten(item['text'])} ({item['reason']}; {item['finding_id']}; {cite_text(item['source'], item['locator'])})")
    else:
        lines.append("- Nothing was flagged as regulatory, pricing or engineering-internal.")
    return "\n".join(lines)


def load_accepted_clusters(conn: Any, run_id: str) -> list[dict[str, Any]]:
    """Clusters from the run's accepted steps, each with its linked findings."""
    rows = conn.execute(
        "select c.id, c.label, d.key, d.label, c.ontology_domain_id, f.id, f.locator, f.text, f.signal_type, f.evidence_level, "
        "f.market, f.vehicle_line, f.out_of_scope_reason, f.sample_size, f.assumptions, s.uri, s.input_family "
        "from public.cluster c join public.step st on st.id = c.step_id "
        "left join public.ontology d on d.id = c.ontology_domain_id "
        "join public.cluster_finding cf on cf.cluster_id = c.id join public.finding f on f.id = cf.finding_id "
        "join public.source s on s.id = f.source_id "
        "where st.run_id = %s and st.status = 'accepted' order by c.created_at, c.id, f.created_at, f.id",
        (run_id,),
    ).fetchall()
    keys = (
        "id", "locator", "text", "signal_type", "evidence_level", "market", "vehicle_line", "out_of_scope_reason",
        "sample_size", "assumptions", "source", "input_family",
    )
    clusters: dict[str, dict[str, Any]] = {}
    for row in rows:
        cluster = clusters.setdefault(
            str(row[0]),
            {
                "id": str(row[0]),
                "label": row[1],
                "domain_key": row[2],
                "domain_label": row[3],
                "ontology_domain_id": str(row[4]) if row[4] else None,
                "members": [],
            },
        )
        cluster["members"].append(dict(zip(keys, (str(row[5]), *row[6:]))))
    return list(clusters.values())


def store_result(conn: Any, result: DraftingResult, run_id: str | None, step_id: str | None, origin: str = "pm_query") -> None:
    with conn.transaction():
        stored_step_id = ensure_step(conn, AGENT_NAME, STAGE, run_id, step_id, result.summary)
        domain_ids = {
            row[0]: row[1]
            for row in conn.execute("select key, id from public.ontology where kind = 'domain' and parent_id is null").fetchall()
        }
        for req in result.requirements:
            saved = conn.execute(
                "insert into public.requirement (id, title, description, ontology_domain_id, markets, vehicle_line, metric, "
                "acceptance_criteria, evidence_level, assumptions, uncertainties, status, origin, created_by_run_id, step_id) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "on conflict (id) do update set title = excluded.title, description = excluded.description, "
                "ontology_domain_id = excluded.ontology_domain_id, markets = excluded.markets, vehicle_line = excluded.vehicle_line, "
                "metric = excluded.metric, acceptance_criteria = excluded.acceptance_criteria, "
                "evidence_level = excluded.evidence_level, assumptions = excluded.assumptions, "
                "uncertainties = excluded.uncertainties, step_id = excluded.step_id "
                "where public.requirement.status = 'draft' returning id",  # leave PM-reviewed requirements untouched
                (
                    req.id,
                    req.title,
                    req.description.text,
                    req.ontology_domain_id or domain_ids.get(req.domain_key),
                    req.markets,
                    req.vehicle_line,
                    req.metric.text if req.metric else None,
                    "\n".join(f"- {c.text}" for c in req.acceptance_criteria) or None,
                    req.evidence_level,
                    req.assumptions,
                    req.uncertainties,
                    req.status.lower(),
                    origin,
                    run_id,
                    stored_step_id,
                ),
            ).fetchone()
            if saved is None:
                continue
            # A retry replaces a draft's provenance too; old links must not survive a revised result.
            conn.execute("delete from public.requirement_finding where requirement_id = %s", (req.id,))
            conn.execute("delete from public.requirement_cluster where requirement_id = %s", (req.id,))
            for finding_id in req.linked_finding_ids:
                conn.execute(
                    "insert into public.requirement_finding (requirement_id, finding_id) values (%s, %s) on conflict do nothing",
                    (req.id, finding_id),
                )
            for cluster_id in req.linked_cluster_ids:
                conn.execute(
                    "insert into public.requirement_cluster (requirement_id, cluster_id) values (%s, %s) on conflict do nothing",
                    (req.id, cluster_id),
                )
        if stored_step_id:
            refs = [
                {"type": "requirement", "id": r.id, "title": r.title, "cluster_id": r.cluster_id, "finding_ids": r.linked_finding_ids, "citations": r.citations}
                for r in result.requirements
            ]
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Requirements Drafting Agent")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--clusters-json", type=Path, help="JSON clusters with their findings; avoids reading the database")
    parser.add_argument("--findings-json", type=Path, help="JSON list of findings for clusters that only carry finding ids")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids the OpenAI call for tests/demos")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing requirements")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    conn = None
    findings = None
    if args.clusters_json:
        clusters = load_clusters(args.clusters_json)
        if args.findings_json:
            payload = json.loads(args.findings_json.read_text(encoding="utf-8"))
            findings = payload.get("findings") if isinstance(payload, dict) else payload
    else:
        if not args.run_id:
            raise SystemExit("Provide --clusters-json, or --run-id to read the run's accepted clusters.")
        conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
        clusters = load_accepted_clusters(conn, args.run_id)
    if not clusters:
        raise SystemExit("No accepted clusters to draft from. Provide --clusters-json or accept a clustering step first.")

    draft = (
        load_drafting_draft(args.draft_json)
        if args.draft_json
        else draft_requirements_with_openai(require_openai()(), args.vehicle_line, args.market, clusters, findings)
    )
    result = build_result(args.vehicle_line, args.market, clusters, draft, findings)

    if args.dry_run:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    conn = conn or require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, result, args.run_id, args.step_id)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
