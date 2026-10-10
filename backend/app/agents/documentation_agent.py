"""Documentation Agent (stage 05).

Compiles the accepted steps of a run and the PM's decisions into a human-readable dossier
(markdown) with the audit trail. A statement only enters the dossier if it cites a finding that
was retrieved and accepted in the same run; rejected or unreviewed steps become coverage gaps.
The compilation is plain code, no model writes text, so nothing uncited can slip in. The dossier
is split into sections that can be re-embedded into the knowledge layer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TYPE_CHECKING

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

AGENT_NAME = "Documentation Agent"
STAGE = 5
EMBED_MODEL = "text-embedding-3-small"
MAX_EMBED_CHARS = 6000
DOSSIER_SOURCE_TYPE = "dossier"

SECTIONS = {
    "evidence": "Evidence",
    "themes": "Themes",
    "requirements": "Draft requirements",
    "scores": "Proposed scores",
    "out_of_scope": "Out of scope (flagged)",
}
GAP_HEADING_RE = re.compile(r"confidence|gaps?|missing|thin", re.IGNORECASE)
MARKER_RE = re.compile(r"\[([^\[\]]+)\]")
NON_PM_ACTORS = {"orchestrator", "system"}

Embedder = Callable[[list[str]], list[list[float]]]


@dataclass
class DossierStatement:
    section: str
    text: str
    step_id: str
    agent_name: str
    finding_ids: list[str]
    citations: list[dict[str, Any]]


@dataclass
class DossierChunk:
    heading: str
    content: str
    finding_ids: list[str]


@dataclass
class DocumentationResult:
    agent_name: str
    vehicle_line: str
    market: str
    run_id: str | None
    query: str
    compiled_at: str
    steps_read: int
    steps_compiled: int
    statements: list[DossierStatement]
    coverage_gaps: list[str]
    audit_trail: list[dict[str, Any]]
    dossier: str
    chunks: list[DossierChunk]
    summary: str


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in values) + "]"


def citation_of(finding: dict[str, Any]) -> dict[str, Any] | None:
    """The id and locator a claim is traced by, or None when the finding cannot be cited."""
    finding_id = finding.get("id") or finding.get("finding_id")
    locator = finding.get("locator")
    if not finding_id or not locator:
        return None
    source = finding.get("source") or finding.get("source_file") or finding.get("source_url") or finding.get("file")
    return {
        "finding_id": str(finding_id),
        "source": str(source or ""),
        "locator": str(locator),
        "evidence_level": finding.get("evidence_level"),
    }


def cite_text(citation: dict[str, Any]) -> str:
    """`F-101: file, locator` for a summary bullet; web locators already contain their URL."""
    where = citation["locator"] if citation["source"] in citation["locator"] else f"{citation['source']}, {citation['locator']}"
    return f"{citation['finding_id']}: {where}"


def plain(value: Any) -> str:
    """Text of a field that may be a string, a cited statement ({"text": ...}) or a list of either."""
    if isinstance(value, dict):
        return str(value.get("text") or "")
    if isinstance(value, list):
        return "; ".join(plain(v) for v in value)
    return str(value or "")


def step_output(step: dict[str, Any]) -> dict[str, Any]:
    """A step's structured output: `output` (or `result`), e.g. `dataclasses.asdict` of an agent result."""
    return step.get("output") or step.get("result") or {}


def is_pm(actor: str) -> bool:
    return not actor.endswith("Agent") and actor.lower() not in NON_PM_ACTORS


def summary_gaps(summary: str) -> list[str]:
    """The bullets a step listed under its confidence/gaps heading."""
    gaps: list[str] = []
    collecting = False
    for line in summary.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and not stripped.startswith("-"):
            collecting = bool(GAP_HEADING_RE.search(stripped))
        elif collecting and stripped.startswith("- "):
            gaps.append(stripped[2:])
    return gaps


def build_audit_trail(steps: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Audit rows in time order: who or what changed what, when, and the recorded rationale.

    A step the PM resolved without a matching event in `decisions` still gets its row, taken from
    the step's own `resolved_by`, `resolved_at` and `pm_note`.
    """
    rows = [
        {
            "timestamp": str(event.get("timestamp") or event.get("created_at") or ""),
            "actor": str(event.get("actor") or ""),
            "action": str(event.get("action") or ""),
            "entity_type": event.get("entity_type"),
            "entity_id": str(event["entity_id"]) if event.get("entity_id") else None,
            "rationale": event.get("rationale"),
            "before": event.get("before"),
            "after": event.get("after"),
        }
        for event in decisions
    ]
    resolved = {(row["entity_id"], row["action"]) for row in rows}
    for step in steps:
        action = {"accepted": "accept", "rejected": "reject"}.get(str(step.get("status")))
        if not action or not step.get("resolved_at"):
            continue
        if any(entity_id == str(step.get("id")) and action in recorded for entity_id, recorded in resolved):
            continue
        rows.append({
            "timestamp": str(step["resolved_at"]),
            "actor": str(step.get("resolved_by") or "pm"),
            "action": f"{action} step {step.get('agent_name')}",
            "entity_type": "step",
            "entity_id": str(step.get("id")),
            # pm_note is the latest steering note; on an accepted step it is a retry note, not a reason
            "rationale": step.get("pm_note") if action == "reject" else None,
            "before": None,
            "after": {"status": step.get("status")},
        })
    return sorted(rows, key=lambda row: row["timestamp"])


def compile_statements(steps: list[dict[str, Any]]) -> tuple[list[DossierStatement], dict[str, dict[str, Any]], list[str]]:
    """Statements from accepted steps only, plus the coverage gaps found on the way."""
    gaps: list[str] = []
    accepted = [s for s in steps if s.get("status") == "accepted"]
    for step in steps:
        name = str(step.get("agent_name"))
        if step.get("status") == "rejected":
            note = f": {step['pm_note']}" if step.get("pm_note") else ""
            gaps.append(f"{name} was rejected{note}. Its contribution is missing from everything downstream.")
        elif step.get("status") != "accepted":
            gaps.append(f"{name} is {step.get('status')}, not accepted, so its output is not part of this dossier.")

    # Only findings that an accepted step produced can be cited anywhere in the dossier.
    citable: dict[str, dict[str, Any]] = {}
    for step in accepted:
        uncitable = 0
        for finding in step_output(step).get("findings") or []:
            cited = citation_of(finding)
            if cited is None:
                uncitable += 1
            else:
                citable[cited["finding_id"]] = cited
        if uncitable:
            gaps.append(f"{step.get('agent_name')}: {uncitable} finding(s) have no id or locator and were left out.")

    statements: list[DossierStatement] = []

    def add(section: str, step: dict[str, Any], label: str, text: str, finding_ids: list[Any]) -> None:
        wanted = list(dict.fromkeys(str(i) for i in finding_ids or []))
        kept = [i for i in wanted if i in citable]
        removed = [i for i in wanted if i not in citable]
        if not kept:
            gaps.append(f"{label} was left out: none of its findings were retrieved and accepted in this run.")
            return
        if removed:
            gaps.append(f"{label}: citation(s) to {', '.join(removed)} removed, not retrieved and accepted in this run.")
        statements.append(DossierStatement(
            section=section,
            text=" ".join(text.split()),
            step_id=str(step.get("id")),
            agent_name=str(step.get("agent_name")),
            finding_ids=kept,
            citations=[citable[i] for i in kept],
        ))

    for step in accepted:
        output = step_output(step)
        for finding in output.get("findings") or []:
            cited = citation_of(finding)
            if cited is None:
                continue
            if finding.get("out_of_scope_reason"):
                text = f"{finding.get('text', '')} Routed out of scope: {finding['out_of_scope_reason']}."
                add("out_of_scope", step, cited["finding_id"], text, [cited["finding_id"]])
            else:
                add("evidence", step, cited["finding_id"], str(finding.get("text") or ""), [cited["finding_id"]])
        for cluster in output.get("clusters") or []:
            members = cluster.get("member_finding_ids") or cluster.get("finding_ids") or []
            add("themes", step, f"Theme '{cluster.get('label')}'",
                f"Theme '{cluster.get('label')}' groups {len(members)} finding(s).", members)
        for requirement in output.get("requirements") or []:
            label = str(requirement.get("code") or requirement.get("id"))
            parts = [f"{label} {requirement.get('title', '')}: {plain(requirement.get('description'))}"]
            for name, key in (("Metric", "metric"), ("Acceptance criteria", "acceptance_criteria"),
                              ("Assumptions", "assumptions"), ("Uncertainties", "uncertainties")):
                if requirement.get(key):
                    parts.append(f"{name}: {plain(requirement[key]).rstrip('.')}.")
            add("requirements", step, f"Requirement {label}", " ".join(parts),
                requirement.get("linked_finding_ids") or requirement.get("finding_ids") or [])
        for score in output.get("scores") or []:
            label = str(score.get("requirement_code") or score.get("requirement_id"))
            breakdown = "; ".join(
                f"{c['name']} {c['value']:.2f} x {c['weight']:.2f} = {c['contribution']:+.2f}" for c in score.get("breakdown") or []
            )
            text = (
                f"{label} proposed score {score.get('composite', 0):.2f}, {score.get('proposed_tier', 'no tier proposed')}, "
                f"confidence {score.get('confidence', 0):.2f}" + (f" ({breakdown})" if breakdown else "") + f". {score.get('rationale') or ''}"
            )
            add("scores", step, f"Score for {label}", text, score.get("finding_ids") or [])

        gaps.extend(f"{step.get('agent_name')}: {gap}" for gap in summary_gaps(str(step.get("human_readable_summary") or "")))
        if not any(output.get(key) for key in ("findings", "clusters", "requirements", "scores")):
            gaps.append(f"{step.get('agent_name')} was accepted without structured output, so nothing from it could be cited.")

    return statements, citable, list(dict.fromkeys(gaps))


def cell(value: Any) -> str:
    return " ".join(str(value).split()).replace("|", "\\|") if value not in (None, "") else "—"


def render_dossier(
    vehicle_line: str,
    market: str,
    query: str,
    run_id: str | None,
    compiled_at: str,
    steps: list[dict[str, Any]],
    statements: list[DossierStatement],
    gaps: list[str],
    audit_trail: list[dict[str, Any]],
) -> str:
    accepted = [s for s in steps if s.get("status") == "accepted"]
    lines = [
        f"# Research dossier: {query}",
        "",
        f"Scope: {vehicle_line} / {market}." + (f" Run {run_id}." if run_id else "")
        + f" Compiled {compiled_at[:10]} by the {AGENT_NAME} from {len(accepted)} accepted step(s) of {len(steps)}.",
        "Every statement cites findings that were retrieved and accepted in this run. "
        "Markers such as [F-101] resolve under Sources.",
        "",
        "## Accepted steps",
        "",
    ]
    for number, step in enumerate(accepted, 1):
        looked_at = (str(step.get("human_readable_summary") or "").strip().splitlines() or ["no summary"])[0]
        attempt = f", attempt {step['attempt']}" if (step.get("attempt") or 1) > 1 else ""
        by = f", accepted by {step['resolved_by']}" if step.get("resolved_by") else ""
        when = f" on {str(step['resolved_at'])[:16]}" if step.get("resolved_at") else ""
        lines.append(f"{number}. **{step.get('agent_name')}**{attempt}{by}{when}: {looked_at}")
    if not accepted:
        lines.append("No step has been accepted yet.")

    for section, heading in SECTIONS.items():
        in_section = [s for s in statements if s.section == section]
        if not in_section:
            continue
        lines.extend(["", f"## {heading}", ""])
        for statement in in_section:
            markers = " ".join(f"[{i}]" for i in statement.finding_ids)
            lines.append(f"- {statement.text} {markers}")

    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- {gap}" for gap in gaps)
    if not gaps:
        lines.append("None recorded.")

    lines.extend(["", "## Audit trail", ""])
    if audit_trail:
        lines.extend(["| Timestamp | Actor | Action | Rationale |", "|---|---|---|---|"])
        for row in audit_trail:
            lines.append(f"| {cell(row['timestamp'][:16])} | {cell(row['actor'])} | {cell(row['action'])} | {cell(row['rationale'])} |")
    else:
        lines.append("No audit events were passed in.")

    lines.extend(["", "## Sources", ""])
    cited: dict[str, dict[str, Any]] = {}
    for statement in statements:
        for citation in statement.citations:
            cited.setdefault(citation["finding_id"], citation)
    for finding_id, citation in cited.items():
        level = f" ({citation['evidence_level']})" if citation.get("evidence_level") else ""
        lines.append(f"- [{finding_id}] {cite_text(citation).split(': ', 1)[1]}{level}")
    if not cited:
        lines.append("No finding could be cited.")
    return "\n".join(lines) + "\n"


def chunk_dossier(dossier: str, citable_ids: set[str]) -> list[DossierChunk]:
    """One chunk per `##` section, each keeping the finding ids it cites."""
    chunks: list[DossierChunk] = []
    for index, block in enumerate(re.split(r"\n(?=## )", dossier.strip())):
        heading = block.splitlines()[0].lstrip("# ").strip()
        ids = [i for i in dict.fromkeys(MARKER_RE.findall(block)) if i in citable_ids]
        chunks.append(DossierChunk(heading=heading if index else "Overview", content=block.strip(), finding_ids=ids))
    return chunks


def build_result(
    vehicle_line: str,
    market: str,
    query: str,
    steps: list[dict[str, Any]],
    decisions: list[dict[str, Any]] | None = None,
    *,
    run_id: str | None = None,
) -> DocumentationResult:
    """Compile the dossier for one run.

    `steps` are the run's steps as plain dicts (id, agent_name, status, position, attempt,
    human_readable_summary, pm_note, resolved_by, resolved_at) with their structured `output`.
    `decisions` are the run's audit events (timestamp, actor, action, rationale, entity).
    """
    # This agent's own step is the one being produced, not an input.
    ordered = sorted((s for s in steps if s.get("agent_name") != AGENT_NAME), key=lambda s: s.get("position") or 0)
    compiled_at = datetime.now(timezone.utc).isoformat()
    statements, citable, gaps = compile_statements(ordered)
    audit_trail = build_audit_trail(ordered, decisions or [])
    if not audit_trail:
        gaps.append("No audit events or PM decisions were passed in, so the audit trail is empty.")
    dossier = render_dossier(vehicle_line, market, query, run_id, compiled_at, ordered, statements, gaps, audit_trail)
    summary = summarize(vehicle_line, market, query, ordered, statements, gaps, audit_trail)
    return DocumentationResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        run_id=run_id,
        query=query,
        compiled_at=compiled_at,
        steps_read=len(ordered),
        steps_compiled=sum(1 for s in ordered if s.get("status") == "accepted"),
        statements=statements,
        coverage_gaps=gaps,
        audit_trail=audit_trail,
        dossier=dossier,
        chunks=chunk_dossier(dossier, set(citable)),
        summary=summary,
    )


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    steps: list[dict[str, Any]],
    statements: list[DossierStatement],
    gaps: list[str],
    audit_trail: list[dict[str, Any]],
) -> str:
    accepted = sum(1 for s in steps if s.get("status") == "accepted")
    rejected = sum(1 for s in steps if s.get("status") == "rejected")
    pm_decisions = sum(1 for row in audit_trail if is_pm(row["actor"]))
    lines = [
        f"{AGENT_NAME} looked at {len(steps)} step(s) ({accepted} accepted, {rejected} rejected) and "
        f"{len(audit_trail)} audit event(s), {pm_decisions} of them PM decisions, for {vehicle_line} / {market}: {query}",
        "Only accepted steps were compiled, and only findings accepted in this run are cited.",
        "",
        "Dossier contents:",
    ]
    for section, heading in SECTIONS.items():
        in_section = [s for s in statements if s.section == section]
        if not in_section:
            continue
        cited: dict[str, dict[str, Any]] = {}
        for statement in in_section:
            for citation in statement.citations:
                cited.setdefault(citation["finding_id"], citation)
        cites = "; ".join(cite_text(c) for c in cited.values())
        lines.append(f"- {heading}: {len(in_section)} statement(s) ({cites})")
    if not statements:
        lines.append("- No statement could be compiled from accepted, cited output.")
    lines.append(f"- Audit trail: {len(audit_trail)} event(s) in time order.")
    lines.extend(["", "Confidence and gaps:"])
    lines.extend(f"- {gap}" for gap in gaps)
    if not gaps:
        lines.append("- No coverage gaps: every planned step was accepted and every statement kept its citations.")
    return "\n".join(lines)


# ---------------------------------------------------------------- re-embedding and storage

def require_openai() -> Any:
    if OpenAI is None:
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e backend`.")
    return OpenAI


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def openai_embedder(client: "OpenAIClient") -> Embedder:
    def embed(texts: list[str]) -> list[list[float]]:
        data = client.embeddings.create(model=EMBED_MODEL, input=[t[:MAX_EMBED_CHARS] for t in texts]).data
        return [item.embedding for item in data]

    return embed


def embed_chunks(chunks: list[DossierChunk], embedder: Embedder) -> list[list[float]]:
    """One vector per dossier section. The embedder is injected, so tests pass a fake."""
    if not chunks:
        return []
    vectors = embedder([f"{chunk.heading}\n{chunk.content}" for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("embedder returned a different number of vectors than chunks")
    return vectors


def ensure_step(conn: Any, run_id: str | None, step_id: str | None, summary: str) -> str | None:
    if step_id:
        conn.execute(
            "update public.step set status = 'awaiting_review', human_readable_summary = %s where id = %s",
            (summary, step_id),
        )
        return step_id
    if not run_id:
        return None
    return conn.execute(
        "insert into public.step (run_id, agent_name, stage, status, human_readable_summary, launched_by, launched_at, position) "
        "values (%s, %s, %s, 'awaiting_review', %s, %s, now(), "
        "(select coalesce(max(position), 0) + 1 from public.step where run_id = %s)) returning id",
        (run_id, AGENT_NAME, STAGE, summary, AGENT_NAME, run_id),
    ).fetchone()[0]


def store_chunks(conn: Any, result: DocumentationResult, vectors: list[list[float]]) -> None:
    """Write the dossier sections as searchable chunks under one `dossier://` source per run.

    Needs a schema change that is not applied yet: `source.type` must allow 'dossier' (the insert
    fails on the check constraint until then, and the surrounding transaction rolls back).
    """
    uri = f"dossier://run/{result.run_id}"
    row = conn.execute("select id from public.source where uri = %s", (uri,)).fetchone()
    if row:
        source_id = row[0]
        conn.execute("delete from public.chunk where source_id = %s", (source_id,))
    else:
        source_id = conn.execute(
            "insert into public.source (type, uri, vehicle_line, market, title, input_family, origin, added_by, ingest_status) "
            "values (%s, %s, %s, %s, %s, 'internal_data', 'connector', %s, 'succeeded') returning id",
            (DOSSIER_SOURCE_TYPE, uri, result.vehicle_line, result.market, f"Research dossier: {result.query}"[:500], AGENT_NAME),
        ).fetchone()[0]
    for index, (chunk, vector) in enumerate(zip(result.chunks, vectors)):
        conn.execute(
            "insert into public.chunk (source_id, locator, heading, content, chunk_index, embedding) "
            "values (%s, %s, %s, %s, %s, %s::extensions.vector)",
            (source_id, f"dossier section '{chunk.heading}'", chunk.heading, chunk.content, index, vec(vector)),
        )


def store_result(
    conn: Any,
    result: DocumentationResult,
    run_id: str | None,
    step_id: str | None,
    embedder: Embedder | None = None,
) -> None:
    """Leave the step in review with the dossier attached, log the compilation, optionally re-embed.

    Requirements, scores and earlier steps are not touched: accepting the dossier is the PM's call.
    """
    vectors = embed_chunks(result.chunks, embedder) if embedder else []
    with conn.transaction():
        stored_step_id = ensure_step(conn, run_id, step_id, result.summary)
        if stored_step_id:
            refs = [{"type": "dossier", "markdown": result.dossier}] + [
                {"type": "statement", "section": s.section, "finding_ids": s.finding_ids, "citations": s.citations}
                for s in result.statements
            ]
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )
        if run_id:
            after = {"statements": len(result.statements), "coverage_gaps": result.coverage_gaps,
                     "steps_compiled": result.steps_compiled, "re_embedded_chunks": len(vectors)}
            conn.execute(
                "insert into public.audit_event (entity_type, entity_id, actor, action, after, rationale) "
                "values ('pipeline_run', %s, %s, 'dossier_compiled', %s::jsonb, %s)",
                (run_id, AGENT_NAME, json.dumps(after), "Compiled from the accepted steps of the run"),
            )
        if vectors:
            store_chunks(conn, result, vectors)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Documentation Agent")
    parser.add_argument("query", help="the PM research request the run answers")
    parser.add_argument("--input-json", type=Path, required=True, help="the run: {steps: [...], decisions: [...]}")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--reembed", action="store_true", help="embed the dossier sections and store them as chunks")
    parser.add_argument("--markdown", action="store_true", help="with --dry-run, print the dossier instead of JSON")
    parser.add_argument("--dry-run", action="store_true", help="print the result instead of writing it")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    payload = json.loads(args.input_json.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit("Documentation Agent input JSON must be an object")
    result = build_result(
        args.vehicle_line,
        args.market,
        args.query,
        payload.get("steps", []),
        payload.get("decisions", []),
        run_id=args.run_id or payload.get("run_id"),
    )

    if args.dry_run:
        print(result.dossier if args.markdown else json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    embedder = openai_embedder(require_openai()()) if args.reembed else None
    conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, result, args.run_id, args.step_id, embedder)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
