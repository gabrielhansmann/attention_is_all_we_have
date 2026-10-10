"""Baseline Agent.

Stage 01. Reads what the current generation already does well: positive customer comments on the
line, the BMW portfolio documents (catalog text and standard equipment) and the sales volumes so
far. It turns them into `Finding` rows tagged `strategic_continuity`: what must carry over.

Citations are copied from the knowledge-tool hits, never from text the model wrote: a drafted
finding that cites no retrieved row is dropped. The agent only produces findings and a step
summary; it leaves the step in `awaiting_review` for the PM.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

# The evidence pack, citation checks and the finding writer are the same for both internal-data agents.
from app.agents.customer_feedback_agent import (
    ALL,
    Evidence,
    EvidencePack,
    add_hits,
    citation_text,
    cited_evidence,
    clean_assumptions,
    common_value,
    counts_by_key,
    draft_with_openai,
    evidence_blocks,
    evidence_from_hit,
    evidence_level_for,
    joined_locator,
    kind_counts,
    knowledge_tools,
    load_evidence,
    out_of_scope_reason_for,
    require_openai,
    require_psycopg,
    scope_filter,
    scope_label,
    skipped_from_draft,
    store_findings,
)

if TYPE_CHECKING:
    from openai import OpenAI as OpenAIClient

AGENT_NAME = "Baseline Agent"
STAGE = 1
SIGNAL_TYPE = "strategic_continuity"
BASELINE_MODEL = os.getenv("BASELINE_AGENT_MODEL", "gpt-4.1-mini")

CATALOG_GAP = (
    "Catalog pages and option rows come from the German sales catalogs and carry no market; "
    "they show what is offered, not what a specific market wants."
)


@dataclass
class BaselineFinding:
    source_file: str
    locator: str
    text: str
    signal_type: str
    evidence_level: str
    market: str
    vehicle_line: str
    sentiment: float | None
    sample_size: int | None  # positive customer comments cited by this finding
    sample_base: int | None  # all positive comments in scope (exact count)
    polarity: str | None
    citations: list[dict[str, str]]
    snapshot: str
    assumptions: list[str] = field(default_factory=list)
    out_of_scope_reason: str | None = None


@dataclass
class BaselineResult:
    agent_name: str
    vehicle_line: str
    market: str
    query: str
    retrieved_at: str
    evidence_read: int
    counts: dict[str, int]
    findings: list[BaselineFinding]
    skipped: list[dict[str, str]]
    gaps: list[str]
    summary: str


def option_evidence(hit: Any) -> Evidence | None:
    """An option row without its prices: only the variants it is standard on stay in the metadata."""
    evidence = evidence_from_hit(hit)
    if evidence is None:
        return None
    availability = evidence.meta.get("availability") or []
    standard_on = sorted({str(a["variant"]) for a in availability if a.get("status") == "standard" and a.get("variant")})
    evidence.meta = {
        "vehicle_line": evidence.meta.get("vehicle_line"),
        "code": evidence.meta.get("code"),
        "section": evidence.meta.get("section"),
        "standard_on": standard_on,
    }
    return evidence


def collect_evidence(
    tools: Any,
    query: str,
    vehicle_line: str | None,
    market: str | None,
    k: int = 8,
    option_limit: int = 15,
    option_text: str | None = None,
) -> EvidencePack:
    """Read praise, catalog text, standard equipment and sales volumes for the scope."""
    line, mkt = scope_filter(vehicle_line), scope_filter(market)
    hits: list[Evidence] = []
    gaps: list[str] = []

    praise = add_hits(hits, tools.search_feedback(query, line=line, market=mkt, polarity="positive", k=k))
    pages = add_hits(hits, tools.search_docs(query, line=line, k=k))
    options = [option_evidence(h) for h in tools.get_options(line=line, status="standard", text=option_text, limit=option_limit)]
    seen = {(e.kind, e.id) for e in hits}
    option_rows = [e for e in options if e is not None and (e.kind, e.id) not in seen]
    hits.extend(option_rows)
    sales = add_hits(hits, tools.get_sales(line=line, market=mkt))

    counts = counts_by_key(tools.feedback_stats("polarity", line=line, market=mkt))
    if not praise:
        gaps.append(f"No positive customer comments were found for {scope_label(line)} / {scope_label(mkt)}.")
    if not pages and not option_rows:
        gaps.append(f"No catalog pages or standard-equipment rows were found for {scope_label(line)}.")
    else:
        gaps.append(CATALOG_GAP)
    if not sales:
        gaps.append(f"No sales volumes were found for {scope_label(line)} / {scope_label(mkt)}.")
    elif any(e.meta.get("is_forecast") for e in hits if e.kind == "sales"):
        gaps.append("Sales rows include a forecast year; a forecast is an assumption, not a trend so far.")
    return EvidencePack(hits=hits, counts=counts, gaps=gaps)


def load_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{AGENT_NAME} draft JSON must be an object")
    payload.setdefault("findings", [])
    payload.setdefault("skipped", [])
    return payload


def build_prompt(vehicle_line: str, market: str, query: str, pack: EvidencePack) -> str:
    return f"""You are the Baseline Agent for a vehicle requirements pipeline.

Scope:
- vehicle_line: {vehicle_line} (the current generation, whose successor is being specified)
- market: {market}
- PM query: {query}

Task:
- State what the current generation already does well and must carry over, using only the numbered
  evidence below: positive customer comments, catalog pages, standard-equipment rows and sales volumes.
- Each finding is one strength or established offer, in PM-readable English.
- Copy figures exactly from the evidence. Treat a forecast volume as an assumption, not as a trend.
- Do not create requirements, priorities or recommendations.
- Exclude pricing, regulatory, type-approval and engineering-internal topics.
- Every finding must cite at least one evidence index. A statement without evidence is not a finding.

Return strict JSON with this shape:
{{
  "findings": [
    {{
      "evidence": [1, 4],
      "text": "one cited continuity finding",
      "sentiment": 0.5,
      "assumptions": ["what is thin or inferred"]
    }}
  ],
  "skipped": [
    {{"evidence": [2], "reason": "why no usable finding was produced"}}
  ]
}}

Evidence:
{evidence_blocks(pack.hits)}
"""


def build_result(
    vehicle_line: str | None, market: str | None, query: str, pack: EvidencePack, draft: dict[str, Any]
) -> BaselineResult:
    line, mkt = scope_label(vehicle_line), scope_label(market)
    findings: list[BaselineFinding] = []
    skipped: list[dict[str, str]] = []

    for item in draft.get("findings", []):
        cited = cited_evidence(item, pack.hits)
        if not cited:
            skipped.append({"source": "unknown", "reason": "finding cited no retrieved evidence; dropped"})
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            skipped.append({"source": cited[0].citation, "reason": "empty finding text"})
            continue

        finding_line = common_value(cited, "vehicle_line", line)
        assumptions = clean_assumptions(item)
        # Which line precedes the future vehicle is presumed in the docs, so every finding says so.
        assumptions.append(
            f"Assumes {finding_line if finding_line != ALL else 'the cited line'} is the predecessor of the vehicle "
            "being specified; to confirm with BMW."
        )
        if any(e.kind == "sales" and e.meta.get("is_forecast") for e in cited):
            assumptions.append("Cites a forecast sales volume, which is not an observed result.")
        comments = [e for e in cited if e.kind == "feedback"]
        sample_size = len(comments) or None
        if sample_size == 1:
            assumptions.append("Rests on a single customer comment.")

        findings.append(
            BaselineFinding(
                source_file=cited[0].file,
                locator=joined_locator(cited),
                text=text,
                signal_type=SIGNAL_TYPE,
                evidence_level=evidence_level_for(cited),
                market=common_value(cited, "market_code", mkt),
                vehicle_line=finding_line,
                sentiment=item.get("sentiment"),
                sample_size=sample_size,
                sample_base=pack.counts.get("positive") if sample_size else None,
                polarity="positive" if sample_size else None,
                citations=[
                    {"kind": e.kind, "id": e.id, "file": e.file, "locator": e.locator, "quote": e.quote} for e in cited
                ],
                snapshot="\n".join(e.quote for e in cited),
                assumptions=assumptions,
                out_of_scope_reason=out_of_scope_reason_for(text),
            )
        )

    skipped.extend(skipped_from_draft(draft, pack.hits))
    summary = summarize(line, mkt, query, pack, findings, skipped)
    return BaselineResult(
        agent_name=AGENT_NAME,
        vehicle_line=line,
        market=mkt,
        query=query,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        evidence_read=len(pack.hits),
        counts=pack.counts,
        findings=findings,
        skipped=skipped,
        gaps=pack.gaps,
        summary=summary,
    )


def sample_text(finding: BaselineFinding) -> str:
    if finding.sample_size is None:
        return "no customer comments cited"
    if finding.sample_base:
        return f"n={finding.sample_size} cited of {finding.sample_base} positive comments in scope"
    return f"n={finding.sample_size} cited comment(s)"


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    pack: EvidencePack,
    findings: list[BaselineFinding],
    skipped: list[dict[str, str]],
) -> str:
    in_scope = [f for f in findings if not f.out_of_scope_reason]
    out_of_scope = [f for f in findings if f.out_of_scope_reason]
    files = sorted({e.file for e in pack.hits})
    lines = [
        f"{AGENT_NAME} looked at {len(pack.hits)} retrieved rows ({kind_counts(pack.hits)}) "
        f"for {vehicle_line} / {market}: {query}",
        f"Sources: {', '.join(files) or 'none'}. Filters: vehicle line {vehicle_line}, market {market}, "
        "positive comments only, standard equipment only.",
        "",
        "Findings (what must carry over):",
    ]
    if in_scope:
        for f in in_scope:
            lines.append(
                f"- [{f.signal_type}] {f.text} ({f.evidence_level}; market {f.market}; {sample_text(f)}; {citation_text(f)})"
            )
    else:
        lines.append("- No usable continuity findings were produced.")

    lines.extend(["", "Confidence and gaps:"])
    lines.extend(f"- {gap}" for gap in pack.gaps)
    if in_scope:
        lines.append("- Which line precedes the future vehicle is an assumption on every finding; confirm with BMW.")
    uncorroborated = sum(1 for f in in_scope if len(f.citations) == 1)
    if uncorroborated:
        lines.append(f"- {uncorroborated} finding(s) rest on a single cited row and should be corroborated.")
    if skipped:
        lines.append(f"- {len(skipped)} drafted item(s) were skipped or dropped for lack of a citation.")
    if not findings:
        lines.append("- The step needs a different query or a wider scope.")

    lines.extend(["", "Out of scope (routed to the side bin):"])
    if out_of_scope:
        for f in out_of_scope:
            lines.append(f"- {f.text} ({f.out_of_scope_reason}; {citation_text(f)})")
    else:
        lines.append("- Nothing.")
    return "\n".join(lines)


def run_agent(
    query: str,
    vehicle_line: str | None = None,
    market: str | None = None,
    *,
    tools: Any = None,
    client: Any = None,
    pack: EvidencePack | None = None,
    draft: dict[str, Any] | None = None,
    k: int = 8,
    option_text: str | None = None,
) -> BaselineResult:
    """Retrieve, draft and validate. Pass `pack` and/or `draft` to skip the database or the model."""
    if pack is None:
        pack = collect_evidence(tools or knowledge_tools(), query, vehicle_line, market, k=k, option_text=option_text)
    if draft is None:
        if pack.hits:
            prompt = build_prompt(scope_label(vehicle_line), scope_label(market), query, pack)
            draft = draft_with_openai(client or require_openai()(), prompt, BASELINE_MODEL)
        else:
            draft = {"findings": [], "skipped": []}  # nothing retrieved, so nothing may be claimed
    return build_result(vehicle_line, market, query, pack, draft)


def store_result(conn: Any, client: "OpenAIClient", result: BaselineResult, run_id: str | None, step_id: str | None) -> None:
    store_findings(conn, client, AGENT_NAME, STAGE, result, run_id, step_id)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Baseline Agent")
    parser.add_argument("query", help="PM research question or steering note")
    parser.add_argument("--vehicle-line", default=ALL, help="F70|G60|G68|G70, or ALL for no filter")
    parser.add_argument("--market", default=ALL, help="EU|CN|US|RoW, or ALL for no filter")
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--evidence-json", type=Path, help="JSON evidence pack; avoids the database for tests/demos")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids OpenAI extraction for tests/demos")
    parser.add_argument("--option-text", help="German substring to narrow the standard-equipment rows")
    parser.add_argument("--max-hits", type=int, default=8, help="comments and catalog pages retrieved")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    result = run_agent(
        args.query,
        args.vehicle_line,
        args.market,
        pack=load_evidence(args.evidence_json) if args.evidence_json else None,
        draft=load_draft(args.draft_json) if args.draft_json else None,
        k=args.max_hits,
        option_text=args.option_text,
    )

    if args.dry_run:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False, default=str))
        return 0

    client = require_openai()()
    conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, client, result, args.run_id, args.step_id)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
