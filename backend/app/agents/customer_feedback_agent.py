"""Customer Feedback Agent.

Stage 01. Reads the ingested customer comments (`*_feedback_hackathon.xlsx`) and customer-study
cells (`*_customer_studies.xlsx`) through the knowledge tools and turns them into `Finding` rows
tagged `complaint`, `unmet_need` or `praise`, each with its sample size and market.

Citations are copied from the knowledge-tool hits, never from text the model wrote: a drafted
finding that cites no retrieved row is dropped. The agent only produces findings and a step
summary; it leaves the step in `awaiting_review` for the PM.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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

AGENT_NAME = "Customer Feedback Agent"
STAGE = 1
EMBED_MODEL = "text-embedding-3-small"
FEEDBACK_MODEL = os.getenv("CUSTOMER_FEEDBACK_AGENT_MODEL", "gpt-4.1-mini")
MAX_EMBED_CHARS = 6000
MAX_PROMPT_CHARS = 600
MAX_SUMMARY_CITATIONS = 3

ALL = "ALL"
MARKETS = ("EU", "CN", "US", "RoW")
POLARITIES = ("negative", "request", "positive")
SIGNAL_BY_POLARITY = {"negative": "complaint", "request": "unmet_need", "positive": "praise"}
POLARITY_BY_SIGNAL = {signal: polarity for polarity, signal in SIGNAL_BY_POLARITY.items()}

# Rows parsed straight from a table are Verified; a reading of free text is Interpreted (doc 03).
STRUCTURED_KINDS = {"study", "sales", "option"}
EVIDENCE_COLUMN = {
    "feedback": "feedback_raw_id",
    "study": "study_response_id",
    "sales": "sales_volume_id",
    "option": "option_id",
    "pdf_text": "chunk_id",
}

OUT_OF_SCOPE_REASON = "pricing/regulatory/engineering-internal topic; route to out-of-scope bin"
OUT_OF_SCOPE_RE = re.compile(
    r"\b(prices?|priced|pricing|msrp|discounts?|expensive|costs?|leasing|lease rates?|emissions?|"
    r"type[- ]approval|homologation|regulations?|regulatory|compliance|safety standard|tax credit|"
    r"suppliers?|part numbers?|tooling|production process)\b",
    re.IGNORECASE,
)


@dataclass
class Evidence:
    """One retrieved, citable row. Built only from a knowledge-tool hit."""

    kind: str  # feedback | study | sales | option | pdf_text
    id: str
    file: str
    locator: str
    quote: str
    text: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def citation(self) -> str:
        return f"{self.file}, {self.locator}"


@dataclass
class EvidencePack:
    hits: list[Evidence]
    counts: dict[str, int] = field(default_factory=dict)  # exact comment counts per polarity in scope
    gaps: list[str] = field(default_factory=list)


@dataclass
class CustomerFeedbackFinding:
    source_file: str
    locator: str
    text: str
    signal_type: str
    evidence_level: str
    market: str
    vehicle_line: str
    sentiment: float | None
    sample_size: int | None  # customer comments cited by this finding
    sample_base: int | None  # all comments of that polarity in scope (exact count)
    polarity: str | None
    citations: list[dict[str, str]]
    snapshot: str
    assumptions: list[str] = field(default_factory=list)
    out_of_scope_reason: str | None = None


@dataclass
class CustomerFeedbackResult:
    agent_name: str
    vehicle_line: str
    market: str
    query: str
    retrieved_at: str
    evidence_read: int
    counts: dict[str, int]
    findings: list[CustomerFeedbackFinding]
    skipped: list[dict[str, str]]
    gaps: list[str]
    summary: str


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in values) + "]"


def scope_filter(value: str | None) -> str | None:
    """`ALL`, empty or None means no filter."""
    if value is None or not value.strip() or value.strip().upper() == ALL:
        return None
    return value.strip()


def scope_label(value: str | None) -> str:
    return scope_filter(value) or ALL


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def evidence_from_hit(hit: Any) -> Evidence | None:
    """Turn a knowledge-tool `Hit` (or its dict form) into Evidence. No file or locator, no evidence."""
    citation = _field(hit, "citation")
    file, locator = _field(citation, "file"), _field(citation, "locator")
    if not file or not locator:
        return None
    return Evidence(
        kind=str(_field(citation, "kind") or ""),
        id=str(_field(citation, "id") or ""),
        file=str(file),
        locator=str(locator),
        quote=str(_field(citation, "quote") or ""),
        text=str(_field(hit, "text") or ""),
        meta=dict(_field(hit, "meta") or {}),
    )


def add_hits(pack_hits: list[Evidence], hits: list[Any]) -> int:
    """Append new citable hits, skipping rows already in the pack. Returns how many were added."""
    seen = {(e.kind, e.id) for e in pack_hits}
    added = 0
    for hit in hits:
        evidence = evidence_from_hit(hit)
        if evidence is None or (evidence.kind, evidence.id) in seen:
            continue
        seen.add((evidence.kind, evidence.id))
        pack_hits.append(evidence)
        added += 1
    return added


def counts_by_key(rows: list[Any]) -> dict[str, int]:
    return {str(_field(r, "key") or "unclassified"): int(_field(r, "n") or 0) for r in rows}


def knowledge_tools() -> Any:
    """The live retrieval tools. Imported lazily so tests and --dry-run need no database."""
    from app.knowledge import tools

    return tools


def rank_study_hits(query: str, hits: list[Any], limit: int) -> list[Any]:
    """`get_study` matches questions by substring only, so keep the cells whose question shares words
    with the query."""
    words = {w for w in re.findall(r"[a-zäöüß]{3,}", query.lower())}
    scored = []
    for position, hit in enumerate(hits):
        question = str(_field(hit, "text") or "").lower()
        overlap = sum(1 for w in words if w in question)
        if overlap:
            scored.append((-overlap, position, hit))
    return [hit for _, _, hit in sorted(scored, key=lambda s: s[:2])[:limit]]


def collect_evidence(
    tools: Any, query: str, vehicle_line: str | None, market: str | None, k: int = 8, study_limit: int = 12
) -> EvidencePack:
    """Read comments (per polarity) and study cells for the scope, plus the exact counts behind them."""
    line, mkt = scope_filter(vehicle_line), scope_filter(market)
    hits: list[Evidence] = []
    gaps: list[str] = []

    for polarity in POLARITIES:
        add_hits(hits, tools.search_feedback(query, line=line, market=mkt, polarity=polarity, k=k))
    study_rows = tools.get_study(line=line, market=mkt, limit=study_limit * 10)
    study_added = add_hits(hits, rank_study_hits(query, study_rows, study_limit))

    counts = counts_by_key(tools.feedback_stats("polarity", line=line, market=mkt))
    if not sum(counts.values()):
        gaps.append(f"No customer comments exist for {scope_label(line)} / {scope_label(mkt)}.")
    elif mkt is None:
        by_market = counts_by_key(tools.feedback_stats("market_code", line=line))
        missing = [m for m in MARKETS if not by_market.get(m)]
        if missing:
            gaps.append(f"No customer comments for market(s): {', '.join(missing)}.")
    if not study_rows:
        gaps.append(f"No customer-study cells exist for {scope_label(line)} / {scope_label(mkt)}.")
    elif not study_added:
        gaps.append("No customer-study question matched the words of the query.")
    else:
        gaps.append("The customer-study file has no respondent counts, so study findings carry no sample size.")
    return EvidencePack(hits=hits, counts=counts, gaps=gaps)


def load_evidence(path: Path) -> EvidencePack:
    """Evidence fixture: {"hits": [{kind, id, file, locator, quote, text, meta}], "counts": {}, "gaps": []}."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("hits"), list):
        raise ValueError("Evidence JSON must be an object with a `hits` list")
    hits: list[Evidence] = []
    add_hits(hits, [{"citation": item, "text": item.get("text"), "meta": item.get("meta")} for item in payload["hits"]])
    return EvidencePack(
        hits=hits,
        counts={str(k): int(v) for k, v in (payload.get("counts") or {}).items()},
        gaps=[str(g) for g in payload.get("gaps") or []],
    )


def load_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{AGENT_NAME} draft JSON must be an object")
    payload.setdefault("findings", [])
    payload.setdefault("skipped", [])
    return payload


def evidence_blocks(hits: list[Evidence]) -> str:
    blocks = []
    for i, e in enumerate(hits, 1):
        tags = [f"{name}: {e.meta[name]}" for name in ("vehicle_line", "market_code", "polarity", "powertrain") if e.meta.get(name)]
        body = (e.text if e.kind in {"feedback", "pdf_text"} else e.quote)[:MAX_PROMPT_CHARS]
        blocks.append(f"[{i}] kind: {e.kind}\n{chr(10).join(tags)}\ncontent: {body}")
    return "\n\n".join(blocks)


def build_prompt(vehicle_line: str, market: str, query: str, pack: EvidencePack) -> str:
    return f"""You are the Customer Feedback Agent for a vehicle requirements pipeline.

Scope:
- vehicle_line: {vehicle_line}
- market: {market}
- PM query: {query}

Task:
- State what customers say, using only the numbered evidence below: customer comments and customer-study cells.
- signal_type is "complaint" (negative comments), "unmet_need" (requests) or "praise" (positive comments).
- Group comments that say the same thing into one finding and cite every comment it rests on.
- Keep markets apart: do not merge comments from different markets into one finding.
- Do not create requirements, priorities or recommendations.
- Do not state counts or percentages; sample sizes are added from the data.
- Every finding must cite at least one evidence index. A statement without evidence is not a finding.

Return strict JSON with this shape:
{{
  "findings": [
    {{
      "evidence": [1, 4],
      "text": "one cited finding in PM-readable language",
      "signal_type": "complaint",
      "sentiment": -1.0,
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


def require_openai() -> Any:
    if OpenAI is None:
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e backend`.")
    return OpenAI


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def draft_with_openai(client: "OpenAIClient", prompt: str, model: str = FEEDBACK_MODEL) -> dict[str, Any]:
    response = client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)


def cited_evidence(item: dict[str, Any], hits: list[Evidence]) -> list[Evidence]:
    """The retrieved rows a drafted item points at. Unknown indexes are ignored, so they cite nothing."""
    raw = item.get("evidence", item.get("source_index"))
    indexes = raw if isinstance(raw, list) else [raw]
    cited: list[Evidence] = []
    for value in indexes:
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= index <= len(hits) and hits[index - 1] not in cited:
            cited.append(hits[index - 1])
    return cited


def common_value(cited: list[Evidence], name: str, fallback: str) -> str:
    """The one value all cited rows share, else the scope the agent was run with."""
    values = {str(e.meta[name]) for e in cited if e.meta.get(name)}
    return values.pop() if len(values) == 1 else fallback


def evidence_level_for(cited: list[Evidence]) -> str:
    return "Verified" if all(e.kind in STRUCTURED_KINDS for e in cited) else "Interpreted"


def joined_locator(cited: list[Evidence]) -> str:
    """One locator string for the finding row; rows from another file name that file."""
    primary = cited[0].file
    return "; ".join(e.locator if e.file == primary else e.citation for e in cited)


def out_of_scope_reason_for(text: str) -> str | None:
    return OUT_OF_SCOPE_REASON if OUT_OF_SCOPE_RE.search(text) else None


def clean_assumptions(item: dict[str, Any]) -> list[str]:
    return [str(v) for v in item.get("assumptions") or [] if str(v).strip()]


def skipped_from_draft(draft: dict[str, Any], hits: list[Evidence]) -> list[dict[str, str]]:
    skipped = []
    for item in draft.get("skipped", []):
        cited = cited_evidence(item, hits)
        source = cited[0].citation if cited else "unknown"
        skipped.append({"source": source, "reason": str(item.get("reason") or "not usable")})
    return skipped


def build_result(
    vehicle_line: str | None, market: str | None, query: str, pack: EvidencePack, draft: dict[str, Any]
) -> CustomerFeedbackResult:
    line, mkt = scope_label(vehicle_line), scope_label(market)
    findings: list[CustomerFeedbackFinding] = []
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

        assumptions = clean_assumptions(item)
        drafted = item.get("signal_type")
        comments = [e for e in cited if e.kind == "feedback"]
        polarities = Counter(e.meta.get("polarity") for e in comments if e.meta.get("polarity") in SIGNAL_BY_POLARITY)
        if polarities:
            # The label follows the cited comments, not the model: a draft cannot turn praise into a complaint.
            top = max(polarities.values())
            candidates = [SIGNAL_BY_POLARITY[p] for p, n in polarities.items() if n == top]
            signal_type = drafted if drafted in candidates else candidates[0]
            if drafted in POLARITY_BY_SIGNAL and drafted != signal_type:
                assumptions.append(f"Draft labelled this {drafted}; the cited comments are {signal_type}, which was kept.")
            if len(polarities) > 1:
                assumptions.append("Cited comments mix polarities; the label follows the majority.")
        elif drafted in POLARITY_BY_SIGNAL:
            signal_type = drafted
        else:
            skipped.append({"source": cited[0].citation, "reason": "no polarity in the evidence and no valid signal_type"})
            continue

        sample_size = len(comments) or None
        polarity = POLARITY_BY_SIGNAL[signal_type]
        if sample_size is None:
            assumptions.append("Rests on customer-study cells only; the study file has no respondent counts.")
        elif sample_size == 1:
            assumptions.append("Rests on a single customer comment.")

        findings.append(
            CustomerFeedbackFinding(
                source_file=cited[0].file,
                locator=joined_locator(cited),
                text=text,
                signal_type=signal_type,
                evidence_level=evidence_level_for(cited),
                market=common_value(cited, "market_code", mkt),
                vehicle_line=common_value(cited, "vehicle_line", line),
                sentiment=item.get("sentiment"),
                sample_size=sample_size,
                sample_base=pack.counts.get(polarity) if sample_size else None,
                polarity=polarity,
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
    return CustomerFeedbackResult(
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


def citation_text(finding: Any) -> str:
    """Source + locator for a summary bullet, shortened when a finding cites many rows."""
    shown = [f"{c['file']}, {c['locator']}" for c in finding.citations[:MAX_SUMMARY_CITATIONS]]
    more = len(finding.citations) - len(shown)
    return "; ".join(shown) + (f"; +{more} more cited row(s)" if more > 0 else "")


def sample_text(finding: Any) -> str:
    if finding.sample_size is None:
        return "no sample size"
    if finding.sample_base:
        return f"n={finding.sample_size} cited of {finding.sample_base} {finding.polarity} comments in scope"
    return f"n={finding.sample_size} cited comment(s)"


def kind_counts(hits: list[Evidence]) -> str:
    counts = Counter(e.kind for e in hits)
    return ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items())) or "no rows"


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    pack: EvidencePack,
    findings: list[CustomerFeedbackFinding],
    skipped: list[dict[str, str]],
) -> str:
    in_scope = [f for f in findings if not f.out_of_scope_reason]
    out_of_scope = [f for f in findings if f.out_of_scope_reason]
    files = sorted({e.file for e in pack.hits})
    lines = [
        f"{AGENT_NAME} looked at {len(pack.hits)} retrieved rows ({kind_counts(pack.hits)}) "
        f"for {vehicle_line} / {market}: {query}",
        f"Sources: {', '.join(files) or 'none'}. Filters: vehicle line {vehicle_line}, market {market}, "
        "comments searched per polarity (negative, request, positive).",
    ]
    if pack.counts:
        totals = ", ".join(f"{n} {key}" for key, n in pack.counts.items())
        lines.append(f"Comments in scope (exact counts): {totals}.")
    lines.extend(["", "Findings:"])
    if in_scope:
        for f in in_scope:
            lines.append(
                f"- [{f.signal_type}] {f.text} ({f.evidence_level}; market {f.market}; {sample_text(f)}; {citation_text(f)})"
            )
    else:
        lines.append("- No usable customer-feedback findings were produced.")

    lines.extend(["", "Confidence and gaps:"])
    lines.extend(f"- {gap}" for gap in pack.gaps)
    thin = sum(1 for f in in_scope if f.sample_size == 1)
    if thin:
        lines.append(f"- {thin} finding(s) rest on a single comment and should be corroborated.")
    if in_scope:
        lines.append("- Sample sizes count the comments cited, not every comment on the topic; the search returns the closest matches only.")
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
) -> CustomerFeedbackResult:
    """Retrieve, draft and validate. Pass `pack` and/or `draft` to skip the database or the model."""
    if pack is None:
        pack = collect_evidence(tools or knowledge_tools(), query, vehicle_line, market, k=k)
    if draft is None:
        if pack.hits:
            prompt = build_prompt(scope_label(vehicle_line), scope_label(market), query, pack)
            draft = draft_with_openai(client or require_openai()(), prompt)
        else:
            draft = {"findings": [], "skipped": []}  # nothing retrieved, so nothing may be claimed
    return build_result(vehicle_line, market, query, pack, draft)


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
        "insert into public.step (run_id, agent_name, stage, status, human_readable_summary, launched_by, launched_at, position) "
        "values (%s, %s, %s, 'awaiting_review', %s, %s, now(), "
        "(select coalesce(max(position), 0) + 1 from public.step where run_id = %s)) returning id",
        (run_id, agent_name, stage, summary, agent_name, run_id),
    ).fetchone()[0]


def store_findings(conn: Any, client: "OpenAIClient", agent_name: str, stage: int, result: Any, run_id: str | None, step_id: str | None) -> None:
    """Write a result's findings, their `finding_evidence` links and the step summary in one transaction.

    The cited rows were ingested already, so their `source` row must exist; a missing one aborts the write.
    """
    with conn.transaction():
        stored_step_id = ensure_step(conn, agent_name, stage, run_id, step_id, result.summary)
        embeddings = client.embeddings.create(
            model=EMBED_MODEL,
            input=[finding.text[:MAX_EMBED_CHARS] for finding in result.findings] or ["empty"],
        ).data
        refs = []
        for finding, embedding in zip(result.findings, embeddings):
            row = conn.execute("select id from public.source where uri = %s", (finding.source_file,)).fetchone()
            if not row:
                raise RuntimeError(f"No source row for cited file {finding.source_file}")
            source_id = row[0]
            dedupe = hashlib.sha256(f"{agent_name}|{finding.locator}|{finding.text}".encode("utf-8")).hexdigest()
            refs.append({"type": "finding", "locator": finding.locator, "source": finding.source_file})
            if conn.execute("select id from public.finding where dedupe_key = %s", (dedupe,)).fetchone():
                continue
            finding_id = conn.execute(
                "insert into public.finding (source_id, locator, text, signal_type, evidence_level, sentiment, sample_size, "
                "market, vehicle_line, polarity, out_of_scope_reason, extracted_by, step_id, embedding, source_snapshot, "
                "assumptions, dedupe_key) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector,%s,%s,%s) returning id",
                (
                    source_id,
                    finding.locator,
                    finding.text,
                    finding.signal_type,
                    finding.evidence_level,
                    finding.sentiment,
                    finding.sample_size,
                    finding.market,
                    finding.vehicle_line,
                    finding.polarity,
                    finding.out_of_scope_reason,
                    agent_name,
                    stored_step_id,
                    vec(embedding.embedding),
                    finding.snapshot,
                    finding.assumptions,
                    dedupe,
                ),
            ).fetchone()[0]
            for citation in finding.citations:
                column = EVIDENCE_COLUMN[citation["kind"]]  # fixed mapping, never caller text
                conn.execute(
                    f"insert into public.finding_evidence (finding_id, {column}, quote) values (%s, %s, %s)",
                    (finding_id, citation["id"], citation["quote"]),
                )
        if stored_step_id:
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


def store_result(conn: Any, client: "OpenAIClient", result: CustomerFeedbackResult, run_id: str | None, step_id: str | None) -> None:
    store_findings(conn, client, AGENT_NAME, STAGE, result, run_id, step_id)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Customer Feedback Agent")
    parser.add_argument("query", help="PM research question or steering note")
    parser.add_argument("--vehicle-line", default=ALL, help="F70|G60|G68|G70, or ALL for no filter")
    parser.add_argument("--market", default=ALL, help="EU|CN|US|RoW, or ALL for no filter")
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--evidence-json", type=Path, help="JSON evidence pack; avoids the database for tests/demos")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids OpenAI extraction for tests/demos")
    parser.add_argument("--max-hits", type=int, default=8, help="comments retrieved per polarity")
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
