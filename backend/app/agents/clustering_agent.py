"""Clustering Agent (Clustering / Ontology Agent, stage 02).

The agent groups accepted findings into deduplicated clusters mapped onto the domain taxonomy.
The model only proposes theme labels and assignments; code decides (decision 0012): unknown
finding ids are dropped, a finding sits in at most one cluster, duplicates and out-of-scope
findings are removed before clustering and listed, and what stays unassigned is reported.
It produces clusters and a step summary, nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

try:
    import psycopg
except ModuleNotFoundError:  # pragma: no cover - exercised only without installed deps
    psycopg = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover
    def load_dotenv(*_args: Any, **_kwargs: Any) -> None:
        return None

try:
    from openai import OpenAI
except ModuleNotFoundError:  # pragma: no cover
    OpenAI = None

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # repo-root .env, from any working directory

AGENT_NAME = "Clustering Agent"
STAGE = 2
CLUSTERING_MODEL = os.getenv("CLUSTERING_AGENT_MODEL", "gpt-4.1-mini")
MAX_PROMPT_CHARS = 600
MAX_SUMMARY_CHARS = 180

# Fallback copy of the seeded top-level domains (backend/app/ingest/seed_ontology.py). The ontology
# table is the source of truth: pass `domains` (or --domains-json) to use the live taxonomy.
DEFAULT_DOMAINS: list[dict[str, Any]] = [
    {"key": "exterior", "label": "Exterior"},
    {"key": "interior", "label": "Interior"},
    {"key": "powertrain", "label": "Powertrain"},
    {"key": "driver_assistance", "label": "Driver Assistance"},
    {"key": "infotainment", "label": "Infotainment"},
    {"key": "comfort_space", "label": "Comfort & Space"},
    {"key": "usability", "label": "Usability"},
    {"key": "variant_package", "label": "Variant & Package"},
    {"key": "range_charging", "label": "Range & Charging"},
    {"key": "safety", "label": "Safety (out of scope: regulatory/homologation)"},
]
OUT_OF_SCOPE_DOMAINS = {"safety"}  # decision 0007: seeded, but flagged out of scope as regulatory

# Narrower than the web-research pattern: customer comments say "fine" and "for the price" all the
# time without being about fines or pricing, and those must stay clusterable.
OUT_OF_SCOPE_RE = re.compile(
    r"\b(pricing|msrp|discounts?|price (?:list|point|increase|incentive|cut|strategy)s?|business case|"
    r"emissions?|type approval|homologation|regulations?|regulatory|compliance|safety standards?|tax credits?|"
    r"suppliers?)\b",
    re.IGNORECASE,
)
OUT_OF_SCOPE_TEXT_REASON = "pricing/regulatory/engineering-internal topic; route to out-of-scope bin"
OUT_OF_SCOPE_DOMAIN_REASON = "safety domain is regulatory/homologation; route to out-of-scope bin"


@dataclass
class ClusterFinding:
    id: str
    text: str
    signal_type: str
    evidence_level: str
    locator: str
    market: str | None = None
    vehicle_line: str | None = None
    out_of_scope_reason: str | None = None
    source: str | None = None
    domain: str | None = None
    input_family: str | None = None
    sample_size: int | None = None
    assumptions: list[str] = field(default_factory=list)

    @property
    def citation(self) -> str:
        return cite_text(self.source, self.locator)

    @property
    def ref(self) -> dict[str, str]:
        """Citation as data: the finding id with its source and locator exactly as they came in."""
        return {"finding_id": self.id, "source": self.source or "", "locator": self.locator}

    @property
    def source_key(self) -> str:
        return self.source or self.locator


@dataclass
class Cluster:
    id: str
    label: str
    domain_key: str | None
    domain_label: str | None
    ontology_domain_id: str | None
    domain_source: str  # findings | model | unmapped
    member_finding_ids: list[str]
    members: list[ClusterFinding]
    citations: list[dict[str, str]]
    markets: list[str]
    vehicle_lines: list[str]
    signal_types: dict[str, int]
    evidence_levels: dict[str, int]
    independent_sources: int
    input_families: list[str]


@dataclass
class ClusteringResult:
    agent_name: str
    vehicle_line: str
    market: str
    findings_read: int
    clusters: list[Cluster]
    unassigned: list[dict[str, str]]
    out_of_scope: list[dict[str, str]]
    duplicates: list[dict[str, str]]
    dropped: list[dict[str, str]]
    summary: str


def cite_text(source: str | None, locator: str) -> str:
    """Source + locator as one readable citation; web locators already contain their URL."""
    return f"{source}, {locator}" if source and source not in locator else locator


def as_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return dict(vars(obj))


def shorten(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def stable_finding_id(locator: str, text: str) -> str:
    """Id for a finding that has none yet (e.g. a dry-run result that was never stored)."""
    return "f-" + hashlib.sha256(f"{locator}|{text}".encode("utf-8")).hexdigest()[:12]


def coerce_finding(item: Any) -> ClusterFinding:
    data = as_dict(item)
    text = str(data.get("text") or "").strip()
    locator = str(data.get("locator") or "").strip()
    source = data.get("source") or data.get("source_url") or data.get("file") or data.get("source_uri")
    domain = data.get("domain") or data.get("domain_key") or data.get("ontology_domain_id") or data.get("domain_id")
    sample_size = data.get("sample_size")
    return ClusterFinding(
        id=str(data.get("id") or stable_finding_id(locator, text)),
        text=text,
        signal_type=str(data.get("signal_type") or ""),
        evidence_level=str(data.get("evidence_level") or ""),
        locator=locator,
        market=data.get("market"),
        vehicle_line=data.get("vehicle_line"),
        out_of_scope_reason=data.get("out_of_scope_reason") or None,
        source=str(source) if source else None,
        domain=str(domain) if domain else None,
        input_family=data.get("input_family"),
        sample_size=int(sample_size) if sample_size is not None else None,
        assumptions=[str(v) for v in data.get("assumptions") or [] if str(v).strip()],
    )


def normalize_findings(items: list[Any]) -> tuple[list[ClusterFinding], list[dict[str, str]]]:
    """Coerce the input; a finding without text or without a locator cannot be cited, so it is dropped."""
    findings: list[ClusterFinding] = []
    dropped: list[dict[str, str]] = []
    for item in items:
        finding = item if isinstance(item, ClusterFinding) else coerce_finding(item)
        if not finding.text:
            dropped.append({"finding_id": finding.id, "reason": "finding has no text"})
        elif not finding.locator:
            dropped.append({"finding_id": finding.id, "reason": "finding has no locator and cannot be cited"})
        else:
            findings.append(finding)
    return findings, dropped


def normalize_text(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.casefold()).strip()


def dedupe_findings(findings: list[ClusterFinding]) -> tuple[list[ClusterFinding], list[dict[str, str]]]:
    """Remove repeats: the same id, or the same statement cited from the same place.

    The same statement from two different locators is two pieces of evidence and stays.
    """
    unique: list[ClusterFinding] = []
    duplicates: list[dict[str, str]] = []
    by_id: dict[str, str] = {}
    by_content: dict[tuple[str, str, str], str] = {}
    for finding in findings:
        content_key = (normalize_text(finding.text), finding.source or "", finding.locator)
        kept = by_id.get(finding.id) or by_content.get(content_key)
        if kept:
            reason = "same finding id" if finding.id in by_id else "same text at the same locator"
            duplicates.append({**finding.ref, "duplicate_of": kept, "reason": reason})
            continue
        by_id[finding.id] = finding.id
        by_content[content_key] = finding.id
        unique.append(finding)
    return unique, duplicates


def resolve_domain(value: str | None, domains: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Taxonomy entry for a key, an ontology id or a label; None when it is not in the taxonomy."""
    if not value:
        return None
    wanted = str(value).strip().casefold()
    for domain in domains:
        label = str(domain.get("label") or "").casefold()
        # "Safety (out of scope: ...)" is also reachable as "Safety"
        names = {str(domain.get("key") or "").casefold(), str(domain.get("id") or "").casefold(), label, label.split(" (")[0]}
        if wanted in names:
            return domain
    return None


def out_of_scope_reason(finding: ClusterFinding, domains: list[dict[str, Any]]) -> str | None:
    if finding.out_of_scope_reason:
        return finding.out_of_scope_reason
    domain = resolve_domain(finding.domain, domains)
    if domain and domain["key"] in OUT_OF_SCOPE_DOMAINS:
        return OUT_OF_SCOPE_DOMAIN_REASON
    if OUT_OF_SCOPE_RE.search(finding.text):
        return OUT_OF_SCOPE_TEXT_REASON
    return None


def out_of_scope_entry(finding: ClusterFinding, reason: str) -> dict[str, str]:
    flagged_by = "upstream" if finding.out_of_scope_reason else AGENT_NAME
    return {**finding.ref, "text": finding.text, "reason": reason, "flagged_by": flagged_by}


def load_findings(path: Path) -> list[dict[str, Any]]:
    """A JSON list of findings, or an object with a `findings` list (an earlier agent's result)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("findings")
    if not isinstance(payload, list):
        raise ValueError("Findings JSON must be a list of objects or an object with a `findings` list")
    return payload


def load_domains(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(d, dict) and d.get("key") for d in payload):
        raise ValueError("Domains JSON must be a list of objects with at least `key` and `label`")
    return payload


def load_clustering_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Clustering Agent draft JSON must be an object")
    payload.setdefault("clusters", [])
    return payload


def rules_draft(findings: list[Any], domains: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Draft without a model: one cluster per taxonomy domain the findings already carry.

    An explicit choice (--rules), never a silent fallback. Findings without a domain stay unassigned.
    """
    domains = domains or DEFAULT_DOMAINS
    normalized, _ = normalize_findings(findings)
    groups: dict[str, list[str]] = {}
    for finding in normalized:
        domain = resolve_domain(finding.domain, domains)
        if domain:
            groups.setdefault(domain["key"], []).append(finding.id)
    by_key = {d["key"]: d for d in domains}
    return {"clusters": [{"label": by_key[key].get("label") or key, "domain": key, "finding_ids": ids} for key, ids in groups.items()]}


def build_clustering_prompt(vehicle_line: str, market: str, findings: list[ClusterFinding], domains: list[dict[str, Any]]) -> str:
    domain_lines = "\n".join(f"- {d['key']}: {d.get('label') or d['key']}" for d in domains)
    finding_blocks = "\n".join(
        f"[{f.id}] signal_type: {f.signal_type} | evidence: {f.evidence_level} | market: {f.market} | "
        f"domain: {f.domain or 'unknown'}\n{f.text[:MAX_PROMPT_CHARS]}"
        for f in findings
    )
    return f"""You are the Clustering Agent for a vehicle requirements pipeline.

Scope:
- vehicle_line: {vehicle_line}
- market: {market}

Task:
- Group findings that describe the same customer issue or theme into one cluster, across sources.
- Give each cluster a short theme label that only restates what its findings say.
- Map each cluster onto exactly one domain key from the taxonomy below.
- Put every finding id in at most one cluster. Use only the finding ids given.
- Leave a finding out if it fits no theme, and list it under "unassigned" with the reason.
- Do not draft requirements, rank, score or prioritize.

Domain taxonomy:
{domain_lines}

Return strict JSON with this shape:
{{
  "clusters": [
    {{"label": "short theme label", "domain": "domain_key", "finding_ids": ["id", "id"]}}
  ],
  "unassigned": [
    {{"finding_id": "id", "reason": "why it fits no cluster"}}
  ]
}}

Findings:
{finding_blocks}
"""


def require_openai() -> Any:
    if OpenAI is None:
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e backend`.")
    return OpenAI


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def propose_clusters_with_openai(
    client: "OpenAIClient", vehicle_line: str, market: str, findings: list[Any], domains: list[dict[str, Any]] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Ask the model for theme labels and assignments. Only clusterable findings are shown to it.
    `note` is steering from the PM or the Critic on a retry, appended to the task."""
    domains = domains or DEFAULT_DOMAINS
    normalized, _ = normalize_findings(findings)
    unique, _ = dedupe_findings(normalized)
    in_scope = [f for f in unique if not out_of_scope_reason(f, domains)]
    response = client.responses.create(
        model=CLUSTERING_MODEL,
        input=build_clustering_prompt(vehicle_line, market, in_scope, domains) + (f"\n\nSteering for this run:\n{note}" if note else ""),
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)


def cluster_id_for(member_ids: list[str]) -> str:
    """Deterministic uuid from the members, so a re-run or a relabel keeps the same cluster id."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "cluster|" + "|".join(sorted(member_ids))))


def pick_domain(
    members: list[ClusterFinding], proposed: str | None, domains: list[dict[str, Any]]
) -> tuple[dict[str, Any] | None, str]:
    """Domains the findings already carry win over the model's proposal; ties go to the proposal."""
    proposed_domain = resolve_domain(proposed, domains)
    counts = Counter(d["key"] for d in (resolve_domain(m.domain, domains) for m in members) if d)
    if counts:
        top = max(counts.values())
        candidates = sorted(key for key, n in counts.items() if n == top)
        key = proposed_domain["key"] if proposed_domain and proposed_domain["key"] in candidates else candidates[0]
        return resolve_domain(key, domains), "findings"
    if proposed_domain:
        return proposed_domain, "model"
    return None, "unmapped"


def make_cluster(label: str, members: list[ClusterFinding], domain: dict[str, Any] | None, domain_source: str) -> Cluster:
    return Cluster(
        id=cluster_id_for([m.id for m in members]),
        label=label,
        domain_key=domain["key"] if domain else None,
        domain_label=(domain.get("label") or domain["key"]) if domain else None,
        ontology_domain_id=str(domain["id"]) if domain and domain.get("id") else None,
        domain_source=domain_source,
        member_finding_ids=[m.id for m in members],
        members=members,
        citations=[m.ref for m in members],
        markets=sorted({m.market for m in members if m.market}),
        vehicle_lines=sorted({m.vehicle_line for m in members if m.vehicle_line}),
        signal_types=dict(Counter(m.signal_type for m in members)),
        evidence_levels=dict(Counter(m.evidence_level for m in members)),
        independent_sources=len({m.source_key for m in members}),
        input_families=sorted({m.input_family for m in members if m.input_family}),
    )


def build_result(
    vehicle_line: str, market: str, findings: list[Any], draft: dict[str, Any], domains: list[dict[str, Any]] | None = None
) -> ClusteringResult:
    domains = domains or DEFAULT_DOMAINS
    normalized, dropped = normalize_findings(findings)
    unique, duplicates = dedupe_findings(normalized)

    out_of_scope: list[dict[str, str]] = []
    in_scope: dict[str, ClusterFinding] = {}
    for finding in unique:
        reason = out_of_scope_reason(finding, domains)
        if reason:
            out_of_scope.append(out_of_scope_entry(finding, reason))
        else:
            in_scope[finding.id] = finding

    excluded = {item["finding_id"]: "finding is out of scope" for item in out_of_scope}
    excluded.update({item["finding_id"]: "finding is a duplicate" for item in duplicates if item["finding_id"] not in in_scope})

    # Validate the model's assignments: first cluster to claim a finding keeps it.
    assigned: dict[str, str] = {}
    groups: dict[str, dict[str, Any]] = {}
    for item in draft.get("clusters") or []:
        label = " ".join(str(item.get("label") or "").split())
        finding_ids = [str(v) for v in item.get("finding_ids") or []]
        if not label:
            dropped.append({"cluster": "(no label)", "reason": "cluster without a label; its findings stay unassigned"})
            continue
        group = groups.setdefault(label.casefold(), {"label": label, "domain": item.get("domain"), "members": []})
        for finding_id in finding_ids:
            if finding_id in excluded:
                dropped.append({"cluster": label, "finding_id": finding_id, "reason": excluded[finding_id]})
            elif finding_id not in in_scope:
                dropped.append({"cluster": label, "finding_id": finding_id, "reason": "unknown finding id"})
            elif finding_id in assigned:
                if assigned[finding_id] != group["label"]:
                    reason = f"already assigned to cluster '{assigned[finding_id]}'"
                    dropped.append({"cluster": label, "finding_id": finding_id, "reason": reason})
            else:
                assigned[finding_id] = group["label"]
                group["members"].append(in_scope[finding_id])

    clusters: list[Cluster] = []
    for group in groups.values():
        members: list[ClusterFinding] = group["members"]
        if not members:
            dropped.append({"cluster": group["label"], "reason": "no valid member findings; cluster not created"})
            continue
        domain, domain_source = pick_domain(members, group["domain"], domains)
        if domain and domain["key"] in OUT_OF_SCOPE_DOMAINS:
            for member in members:
                assigned.pop(member.id, None)
                in_scope.pop(member.id, None)
                out_of_scope.append(out_of_scope_entry(member, OUT_OF_SCOPE_DOMAIN_REASON))
            dropped.append({"cluster": group["label"], "reason": "mapped to an out-of-scope domain; members routed to the out-of-scope bin"})
            continue
        clusters.append(make_cluster(group["label"], members, domain, domain_source))

    model_reasons = {
        str(item.get("finding_id")): str(item.get("reason") or "").strip()
        for item in draft.get("unassigned") or []
        if isinstance(item, dict)
    }
    unassigned = [
        {**finding.ref, "text": finding.text, "reason": model_reasons.get(finding.id) or "not assigned to any cluster"}
        for finding in in_scope.values()
        if finding.id not in assigned
    ]

    summary = summarize(vehicle_line, market, len(findings), clusters, unassigned, out_of_scope, duplicates, dropped)
    return ClusteringResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        findings_read=len(findings),
        clusters=clusters,
        unassigned=unassigned,
        out_of_scope=out_of_scope,
        duplicates=duplicates,
        dropped=dropped,
        summary=summary,
    )


def counts_text(counts: dict[str, int]) -> str:
    return ", ".join(f"{key or 'unknown'} {n}" for key, n in sorted(counts.items()))


def summarize(
    vehicle_line: str,
    market: str,
    findings_read: int,
    clusters: list[Cluster],
    unassigned: list[dict[str, str]],
    out_of_scope: list[dict[str, str]],
    duplicates: list[dict[str, str]],
    dropped: list[dict[str, str]],
) -> str:
    clustered = sum(len(c.members) for c in clusters)
    domain_count = len({c.domain_key for c in clusters if c.domain_key})
    lines = [
        f"{AGENT_NAME} looked at {findings_read} accepted finding(s) for {vehicle_line} / {market} and grouped "
        f"{clustered} of them into {len(clusters)} cluster(s) across {domain_count} taxonomy domain(s).",
        "",
        "Clusters:",
    ]
    if clusters:
        for cluster in clusters:
            lines.append(
                f"- {cluster.label} [{cluster.domain_label or 'no domain'}]: {len(cluster.members)} finding(s) from "
                f"{cluster.independent_sources} independent source(s); {counts_text(cluster.signal_types)}; "
                f"{counts_text(cluster.evidence_levels)}"
            )
            for member in cluster.members:
                lines.append(f"  - {shorten(member.text)} ({member.evidence_level}; {member.id}; {member.citation})")
    else:
        lines.append("- No clusters were produced.")

    lines.extend(["", "Confidence and gaps:"])
    gaps: list[str] = []
    thin = [c.label for c in clusters if len(c.members) == 1 or c.independent_sources == 1]
    if thin:
        gaps.append(f"- Thin, resting on one finding or one source: {', '.join(thin)}.")
    trend_only = [c.label for c in clusters if set(c.signal_types) == {"market_trend"}]
    if trend_only:
        gaps.append(f"- Only market-trend evidence (assumption about the future, not observed fact): {', '.join(trend_only)}.")
    unmapped = [c.label for c in clusters if not c.domain_key]
    if unmapped:
        gaps.append(f"- No taxonomy domain could be confirmed for: {', '.join(unmapped)}.")
    model_mapped = [c.label for c in clusters if c.domain_source == "model"]
    if model_mapped:
        gaps.append(f"- Domain proposed by the model, not carried by the findings: {', '.join(model_mapped)}.")
    for item in unassigned:
        gaps.append(f"- Unassigned: {shorten(item['text'])} ({item['reason']}; {item['finding_id']}; {cite_text(item['source'], item['locator'])})")
    if duplicates:
        gaps.append(f"- {len(duplicates)} duplicate finding(s) removed: " + ", ".join(f"{d['finding_id']} ({cite_text(d['source'], d['locator'])})" for d in duplicates) + ".")
    if dropped:
        gaps.append(f"- {len(dropped)} proposed assignment(s) or input(s) were dropped by validation (see `dropped`).")
    if not clusters:
        gaps.append("- The step needs more accepted findings or a steering note.")
    lines.extend(gaps or ["- Every in-scope finding is in exactly one cluster, each drawing on more than one source."])

    lines.extend(["", "Out of scope (routed to the side bin, not clustered):"])
    if out_of_scope:
        for item in out_of_scope:
            lines.append(f"- {shorten(item['text'])} ({item['reason']}; {item['finding_id']}; {cite_text(item['source'], item['locator'])})")
    else:
        lines.append("- Nothing was flagged as regulatory, pricing or engineering-internal.")
    return "\n".join(lines)


def ensure_step(conn: Any, agent_name: str, stage: int, run_id: str | None, step_id: str | None, summary: str) -> str | None:
    if step_id:
        conn.execute(
            "update public.step set status = 'awaiting_review', human_readable_summary = %s where id = %s",
            (summary, step_id),
        )
        return step_id
    if not run_id:
        return None
    return conn.execute(
        "insert into public.step (run_id, agent_name, stage, position, status, human_readable_summary, launched_by, launched_at) "
        "values (%s, %s, %s, (select coalesce(max(position), 0) + 1 from public.step where run_id = %s), "
        "'awaiting_review', %s, %s, now()) returning id",
        (run_id, agent_name, stage, run_id, summary, agent_name),
    ).fetchone()[0]


def scope_value(value: str | None) -> str | None:
    return None if not value or value.upper() == "ALL" else value


def load_accepted_findings(conn: Any, vehicle_line: str | None, market: str | None, run_id: str | None = None) -> list[dict[str, Any]]:
    """Findings from accepted steps (or loaded outside a step), optionally limited to one run and scope."""
    rows = conn.execute(
        "select f.id, f.locator, f.text, f.signal_type, f.evidence_level, f.market, f.vehicle_line, f.out_of_scope_reason, "
        "f.sample_size, f.assumptions, s.uri, s.input_family, coalesce(p.key, d.key) "
        "from public.finding f join public.source s on s.id = f.source_id "
        "left join public.step st on st.id = f.step_id "
        "left join public.ontology d on d.id = f.domain_id left join public.ontology p on p.id = d.parent_id "
        "where (f.step_id is null or st.status = 'accepted') "
        "and (%(run)s::uuid is null or st.run_id = %(run)s) "
        "and (%(line)s::text is null or f.vehicle_line = %(line)s) "
        "and (%(market)s::text is null or f.market = %(market)s) order by f.created_at, f.id",
        {"run": run_id, "line": scope_value(vehicle_line), "market": scope_value(market)},
    ).fetchall()
    keys = (
        "id", "locator", "text", "signal_type", "evidence_level", "market", "vehicle_line", "out_of_scope_reason",
        "sample_size", "assumptions", "source", "input_family", "domain",
    )
    return [dict(zip(keys, (str(row[0]), *row[1:]))) for row in rows]


def store_result(conn: Any, result: ClusteringResult, run_id: str | None, step_id: str | None) -> None:
    with conn.transaction():
        stored_step_id = ensure_step(conn, AGENT_NAME, STAGE, run_id, step_id, result.summary)
        domain_ids = {
            row[0]: row[1]
            for row in conn.execute("select key, id from public.ontology where kind = 'domain' and parent_id is null").fetchall()
        }
        for cluster in result.clusters:
            conn.execute(
                "insert into public.cluster (id, label, ontology_domain_id, step_id) values (%s, %s, %s, %s) "
                "on conflict (id) do update set label = excluded.label, ontology_domain_id = excluded.ontology_domain_id, "
                "step_id = excluded.step_id",
                (cluster.id, cluster.label, cluster.ontology_domain_id or domain_ids.get(cluster.domain_key), stored_step_id),
            )
            conn.execute("delete from public.cluster_finding where cluster_id = %s", (cluster.id,))
            for finding_id in cluster.member_finding_ids:
                conn.execute(
                    "insert into public.cluster_finding (cluster_id, finding_id) values (%s, %s)", (cluster.id, finding_id)
                )
        # The regulatory guardrail: findings this agent flagged move to the visible out-of-scope bin.
        for item in result.out_of_scope:
            if item["flagged_by"] == AGENT_NAME:
                conn.execute(
                    "update public.finding set out_of_scope_reason = %s where id = %s and out_of_scope_reason is null",
                    (item["reason"], item["finding_id"]),
                )
        if stored_step_id:
            refs = [
                {"type": "cluster", "id": c.id, "label": c.label, "finding_ids": c.member_finding_ids, "citations": c.citations}
                for c in result.clusters
            ]
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Clustering Agent")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--findings-json", type=Path, help="JSON list of accepted findings; avoids reading the database")
    parser.add_argument("--domains-json", type=Path, help="JSON list of taxonomy domains (key, label, id); default is the seeded list")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids the OpenAI call for tests/demos")
    parser.add_argument("--rules", action="store_true", help="group by the domain the findings carry, without a model")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing clusters")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    conn = None
    if args.findings_json:
        findings = load_findings(args.findings_json)
    else:
        conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
        findings = load_accepted_findings(conn, args.vehicle_line, args.market, args.run_id)
    if not findings:
        raise SystemExit("No accepted findings to cluster. Provide --findings-json or accept a research step first.")

    domains = load_domains(args.domains_json) if args.domains_json else DEFAULT_DOMAINS
    if args.draft_json:
        draft = load_clustering_draft(args.draft_json)
    elif args.rules:
        draft = rules_draft(findings, domains)
    else:
        draft = propose_clusters_with_openai(require_openai()(), args.vehicle_line, args.market, findings, domains)
    result = build_result(args.vehicle_line, args.market, findings, draft, domains)

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
