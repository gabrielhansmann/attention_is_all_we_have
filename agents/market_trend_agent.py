"""Market & Trend Agent.

The agent turns cited web trend evidence into `Finding` rows. It follows the same
Source -> Finding[] contract as the ingestion loaders, but keeps the PM review
boundary intact by only producing findings and a step summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

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

load_dotenv(".env")

AGENT_NAME = "Market & Trend Agent"
EMBED_MODEL = "text-embedding-3-small"
RESEARCH_MODEL = os.getenv("RESEARCH_AGENT_MODEL", "gpt-4.1-mini")
MAX_EMBED_CHARS = 6000

TRUST_BY_DOMAIN_HINT = {
    "bmw": "oem",
    "mercedes-benz": "oem",
    "audi": "oem",
    "tesla": "oem",
    "volkswagen": "oem",
    "volvo": "oem",
    "hyundai": "oem",
    "kia": "oem",
    "toyota": "oem",
    "lexus": "oem",
    "honda": "oem",
    "nissan": "oem",
    "byd": "oem",
    "nio": "oem",
    "rivian": "oem",
}

TRADE_PRESS_HINTS = {
    "automotive",
    "autocar",
    "caranddriver",
    "motortrend",
    "topgear",
    "insideevs",
    "electrive",
    "wardsauto",
    "autonews",
    "carscoops",
    "edmunds",
}

OUT_OF_SCOPE_RE = re.compile(
    r"\b(price|pricing|msrp|discount|emissions?|type approval|homologation|regulation|regulatory|"
    r"mandatory|compliance|safety standard|fine|tax credit)\b",
    re.IGNORECASE,
)


@dataclass
class SourceDoc:
    url: str
    title: str
    snippet: str
    published_at: str | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    language: str | None = None
    trust_tier: str | None = None

    @property
    def domain(self) -> str:
        return urlparse(self.url).netloc.lower().removeprefix("www.")


@dataclass
class MarketTrendFinding:
    source_url: str
    title: str
    retrieved_at: str
    locator: str
    text: str
    signal_type: str
    evidence_level: str
    market: str
    vehicle_line: str
    sentiment: float | None
    trust_tier: str
    snapshot: str
    assumptions: list[str] = field(default_factory=list)
    out_of_scope_reason: str | None = None


@dataclass
class MarketTrendResult:
    agent_name: str
    vehicle_line: str
    market: str
    query: str
    retrieved_at: str
    sources_read: int
    findings: list[MarketTrendFinding]
    skipped: list[dict[str, str]]
    summary: str


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in values) + "]"


def stable_locator(doc: SourceDoc) -> str:
    retrieved_date = doc.retrieved_at[:10]
    return f"{doc.url} · retrieved {retrieved_date}"


def infer_trust_tier(doc: SourceDoc) -> str:
    if doc.trust_tier in {"oem", "trade_press", "forum_social"}:
        return doc.trust_tier
    domain = doc.domain
    if any(hint in domain for hint in TRUST_BY_DOMAIN_HINT):
        return "oem"
    if any(hint in domain for hint in TRADE_PRESS_HINTS):
        return "trade_press"
    return "forum_social"


def evidence_from_trust(trust_tier: str) -> str:
    if trust_tier == "oem":
        return "Verified"
    if trust_tier == "trade_press":
        return "Interpreted"
    return "Unverified"


def normalize_signal_type(value: str | None) -> str:
    if value in {"market_trend", "competitor_advantage"}:
        return value
    return "market_trend"


def load_seed_sources(path: Path) -> list[SourceDoc]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Seed source JSON must be a list of objects")
    docs = []
    for item in payload:
        docs.append(
            SourceDoc(
                url=str(item["url"]),
                title=str(item.get("title") or item["url"]),
                snippet=str(item.get("snippet") or item.get("content") or ""),
                published_at=item.get("published_at"),
                language=item.get("language"),
                trust_tier=item.get("trust_tier"),
            )
        )
    return docs


def load_market_trend_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Market & Trend Agent draft JSON must be an object")
    payload.setdefault("findings", [])
    payload.setdefault("skipped", [])
    return payload


def build_market_trend_prompt(vehicle_line: str, market: str, query: str, docs: list[SourceDoc]) -> str:
    source_blocks = "\n\n".join(
        f"[{i}] title: {doc.title}\nurl: {doc.url}\nretrieved_at: {doc.retrieved_at}\n"
        f"trust_tier: {infer_trust_tier(doc)}\nsnippet: {doc.snippet[:1800]}"
        for i, doc in enumerate(docs, 1)
    )
    return f"""You are the Market & Trend Agent for a vehicle requirements pipeline.

Scope:
- vehicle_line: {vehicle_line}
- market: {market}
- PM query: {query}

Task:
- Extract only vehicle/customer-facing market or technology trend findings.
- Mark future-looking claims as assumptions, not observed facts.
- Do not create requirements or priorities.
- Exclude pricing, regulatory, type-approval, emissions-compliance, or engineering-internal topics.
- Every finding must cite exactly one source index from the provided sources.

Return strict JSON with this shape:
{{
  "findings": [
    {{
      "source_index": 1,
      "text": "one cited finding in PM-readable language",
      "signal_type": "market_trend",
      "sentiment": -1.0,
      "assumptions": ["why this is future-looking or thin"]
    }}
  ],
  "skipped": [
    {{"source_index": 1, "reason": "why no usable finding was produced"}}
  ]
}}

Sources:
{source_blocks}
"""


def require_openai() -> Any:
    if OpenAI is None:
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -r ingest/requirements.txt`.")
    return OpenAI


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -r ingest/requirements.txt`.")
    return psycopg


def extract_market_trends_with_openai(
    client: "OpenAIClient", vehicle_line: str, market: str, query: str, docs: list[SourceDoc]
) -> dict[str, Any]:
    prompt = build_market_trend_prompt(vehicle_line, market, query, docs)
    response = client.responses.create(
        model=RESEARCH_MODEL,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)


def collect_with_web_search(client: "OpenAIClient", vehicle_line: str, market: str, query: str, limit: int) -> list[SourceDoc]:
    search_query = f"{vehicle_line} {market} automotive customer trends {query}"
    response = client.responses.create(
        model=RESEARCH_MODEL,
        tools=[{"type": "web_search_preview"}],
        input=(
            "Search the web for current, citable automotive market or technology trend sources. "
            f"Scope: vehicle line {vehicle_line}, market {market}. Query: {search_query}. "
            f"Return up to {limit} results as JSON: "
            '{"sources":[{"url":"...","title":"...","snippet":"...","published_at":null,"language":null}]}'
        ),
        text={"format": {"type": "json_object"}},
    )
    payload = json.loads(response.output_text)
    docs = []
    for item in payload.get("sources", [])[:limit]:
        if item.get("url") and item.get("snippet"):
            docs.append(
                SourceDoc(
                    url=str(item["url"]),
                    title=str(item.get("title") or item["url"]),
                    snippet=str(item["snippet"]),
                    published_at=item.get("published_at"),
                    language=item.get("language"),
                )
            )
    return docs


def build_result(vehicle_line: str, market: str, query: str, docs: list[SourceDoc], draft: dict[str, Any]) -> MarketTrendResult:
    findings: list[MarketTrendFinding] = []
    skipped: list[dict[str, str]] = []

    for item in draft.get("findings", []):
        source_index = int(item.get("source_index", 0))
        if source_index < 1 or source_index > len(docs):
            skipped.append({"source": "unknown", "reason": "finding referenced an invalid source_index"})
            continue
        doc = docs[source_index - 1]
        text = str(item.get("text") or "").strip()
        if not text:
            skipped.append({"source": doc.url, "reason": "empty finding text"})
            continue

        trust_tier = infer_trust_tier(doc)
        out_of_scope_reason = None
        if OUT_OF_SCOPE_RE.search(text):
            out_of_scope_reason = "pricing/regulatory/engineering-internal topic; route to out-of-scope bin"

        findings.append(
            MarketTrendFinding(
                source_url=doc.url,
                title=doc.title,
                retrieved_at=doc.retrieved_at,
                locator=stable_locator(doc),
                text=text,
                signal_type=normalize_signal_type(item.get("signal_type")),
                evidence_level=evidence_from_trust(trust_tier),
                market=market,
                vehicle_line=vehicle_line,
                sentiment=item.get("sentiment"),
                trust_tier=trust_tier,
                snapshot=doc.snippet,
                assumptions=[str(v) for v in item.get("assumptions", []) if str(v).strip()],
                out_of_scope_reason=out_of_scope_reason,
            )
        )

    for item in draft.get("skipped", []):
        idx = int(item.get("source_index", 0) or 0)
        source = docs[idx - 1].url if 1 <= idx <= len(docs) else "unknown"
        skipped.append({"source": source, "reason": str(item.get("reason") or "not usable")})

    summary = summarize(vehicle_line, market, query, docs, findings, skipped)
    return MarketTrendResult(
        agent_name=AGENT_NAME,
        vehicle_line=vehicle_line,
        market=market,
        query=query,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        sources_read=len(docs),
        findings=findings,
        skipped=skipped,
        summary=summary,
    )


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    docs: list[SourceDoc],
    findings: list[MarketTrendFinding],
    skipped: list[dict[str, str]],
) -> str:
    lines = [
        f"{AGENT_NAME} looked at {len(docs)} web sources for {vehicle_line} / {market}: {query}",
        "",
        "Findings:",
    ]
    if findings:
        for finding in findings:
            scope = "out of scope" if finding.out_of_scope_reason else finding.evidence_level
            lines.append(f"- {finding.text} ({scope}; {finding.locator})")
    else:
        lines.append("- No usable market-trend findings were produced.")
    lines.extend(["", "Confidence and gaps:"])
    if skipped:
        lines.append(f"- {len(skipped)} source(s) were skipped or produced no finding.")
    if any(f.evidence_level == "Unverified" for f in findings):
        lines.append("- Some findings rest on low-trust web/social sources and should be corroborated.")
    if not findings:
        lines.append("- The step needs better sources or a narrower PM steering note.")
    return "\n".join(lines)


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
        "insert into public.step (run_id, agent_name, stage, status, human_readable_summary, launched_by, launched_at) "
        "values (%s, %s, 1, 'awaiting_review', %s, %s, now()) returning id",
        (run_id, AGENT_NAME, summary, AGENT_NAME),
    ).fetchone()[0]


def upsert_source(conn: Any, doc: SourceDoc, vehicle_line: str, market: str, findings_produced: int) -> str:
    trust_tier = infer_trust_tier(doc)
    title = doc.title[:500]
    report = {"items_read": 1, "findings_produced": findings_produced, "items_skipped": 0}
    row = conn.execute("select id from public.source where uri = %s", (doc.url,)).fetchone()
    if row:
        source_id = row[0]
        conn.execute(
            "update public.source set type = 'web', vehicle_line = %s, market = %s, trust_tier = %s, retrieved_at = %s, "
            "title = coalesce(title, %s), input_family = 'website', channel = %s, origin = 'agent_search', "
            "language = coalesce(language, %s), ingest_status = 'succeeded', ingest_report = %s::jsonb where id = %s",
            (
                vehicle_line,
                market,
                trust_tier,
                doc.retrieved_at,
                title,
                doc.domain,
                doc.language,
                json.dumps(report),
                source_id,
            ),
        )
        return source_id
    return conn.execute(
        "insert into public.source (type, uri, vehicle_line, market, trust_tier, retrieved_at, title, input_family, "
        "channel, origin, language, ingest_status, ingest_report) "
        "values ('web', %s, %s, %s, %s, %s, %s, 'website', %s, 'agent_search', %s, 'succeeded', %s::jsonb) returning id",
        (doc.url, vehicle_line, market, trust_tier, doc.retrieved_at, title, doc.domain, doc.language, json.dumps(report)),
    ).fetchone()[0]


def store_result(conn: Any, client: "OpenAIClient", result: MarketTrendResult, run_id: str | None, step_id: str | None) -> None:
    with conn.transaction():
        stored_step_id = ensure_step(conn, run_id, step_id, result.summary)
        embeddings = client.embeddings.create(
            model=EMBED_MODEL,
            input=[finding.text[:MAX_EMBED_CHARS] for finding in result.findings] or ["empty"],
        ).data
        for finding, embedding in zip(result.findings, embeddings):
            doc = SourceDoc(
                url=finding.source_url,
                title=finding.title,
                snippet=finding.snapshot,
                retrieved_at=finding.retrieved_at,
                trust_tier=finding.trust_tier,
            )
            source_id = upsert_source(conn, doc, result.vehicle_line, result.market, 1)
            dedupe = hashlib.sha256(f"{source_id}|{finding.locator}|{finding.text}".encode("utf-8")).hexdigest()
            exists = conn.execute(
                "select id from public.finding where source_id = %s and locator = %s and text = %s",
                (source_id, finding.locator, finding.text),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                "insert into public.finding (source_id, locator, text, signal_type, evidence_level, sentiment, market, "
                "vehicle_line, out_of_scope_reason, extracted_by, step_id, embedding, source_snapshot, assumptions, dedupe_key) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector,%s,%s,%s)",
                (
                    source_id,
                    finding.locator,
                    finding.text,
                    finding.signal_type,
                    finding.evidence_level,
                    finding.sentiment,
                    finding.market,
                    finding.vehicle_line,
                    finding.out_of_scope_reason,
                    AGENT_NAME,
                    stored_step_id,
                    vec(embedding.embedding),
                    finding.snapshot,
                    finding.assumptions,
                    dedupe,
                ),
            )
        if stored_step_id:
            refs = [{"type": "finding", "locator": f.locator, "source": f.source_url} for f in result.findings]
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Market & Trend Agent")
    parser.add_argument("query", help="PM research question or steering note")
    parser.add_argument("--vehicle-line", required=True)
    parser.add_argument("--market", required=True)
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--seed-sources", type=Path, help="JSON list of source snippets; avoids live web search")
    parser.add_argument("--draft-json", type=Path, help="JSON draft output; avoids OpenAI extraction for tests/demos")
    parser.add_argument("--max-sources", type=int, default=6)
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    client = None
    docs = (
        load_seed_sources(args.seed_sources)
        if args.seed_sources
        else collect_with_web_search(require_openai()(), args.vehicle_line, args.market, args.query, args.max_sources)
    )
    if not docs:
        raise SystemExit("No retrievable web sources found. Provide --seed-sources or narrow the query.")

    draft = (
        load_market_trend_draft(args.draft_json)
        if args.draft_json
        else extract_market_trends_with_openai(require_openai()(), args.vehicle_line, args.market, args.query, docs)
    )
    result = build_result(args.vehicle_line, args.market, args.query, docs, draft)

    if args.dry_run:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return 0

    client = require_openai()()
    conn = require_psycopg().connect(os.environ["SUPABASE_DB_URL"])
    store_result(conn, client, result, args.run_id, args.step_id)
    conn.close()
    print(result.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
