"""Sales & Portfolio Agent.

The agent turns sales-volume rows and parsed OptionList rows into revealed-preference `Finding`
rows (`business_signal`). Evidence is read only through the knowledge tools, every number is
computed in code from the cited rows, and the PM review boundary stays intact: the agent only
produces findings and a step summary.
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

AGENT_NAME = "Sales & Portfolio Agent"
EMBED_MODEL = "text-embedding-3-small"
TERMS_MODEL = os.getenv("RESEARCH_AGENT_MODEL", "gpt-4.1-mini")
MAX_EMBED_CHARS = 6000
ALL = "ALL"
CATALOG_MARKET = "EU"  # the OptionList PDFs are German sales catalogs
MAX_OPTION_TERMS = 6

# Option names are German. Safety equipment is regulatory by the ontology seed (decision 0007).
OUT_OF_SCOPE_RE = re.compile(
    r"(\b(price|pricing|msrp|discount|emissions?|type approval|homologation|regulation|regulatory|"
    r"mandatory|compliance|safety standard|tax credit)\b|airbag|sicherheitsgurt|gurtstraffer|kindersitz|"
    r"isofix|reifendruck|notruf|abgas|emission|zulassung|preis)",
    re.IGNORECASE,
)
OUT_OF_SCOPE_REASON = "pricing/regulatory/engineering-internal topic; route to out-of-scope bin"

NO_TAKE_RATE = (
    "Per-option take rates are not in the provided data (sales volumes exist per line, market and year only); "
    "the standard-fitment share across catalog variants is a portfolio proxy for uptake, not a measured take rate."
)


@dataclass
class EvidenceRef:
    kind: str      # sales | option
    id: str
    file: str
    locator: str   # "sheet G60_G68, row 4" or "page 14, SA 0453"
    quote: str


@dataclass
class SalesPortfolioFinding:
    source_file: str
    locator: str
    text: str
    signal_type: str
    evidence_level: str
    market: str
    vehicle_line: str
    sentiment: float | None
    sample_size: int | None
    trust_tier: str | None   # web sources only; always None for provided files
    snapshot: str
    metrics: dict[str, Any] = field(default_factory=dict)
    citations: list[EvidenceRef] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    out_of_scope_reason: str | None = None


@dataclass
class SalesPortfolioResult:
    agent_name: str
    vehicle_line: str
    market: str
    query: str
    retrieved_at: str
    sources_read: int
    filters: dict[str, Any]
    findings: list[SalesPortfolioFinding]
    skipped: list[dict[str, str]]
    summary: str


def vec(values: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in values) + "]"


def scope_filter(value: str | None) -> str | None:
    """`ALL`, empty or None means no filter."""
    if value is None or not str(value).strip() or str(value).strip().upper() == ALL:
        return None
    return str(value).strip()


def scope_label(value: str | None) -> str:
    return scope_filter(value) or ALL


def _get(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def evidence_ref(hit: Any) -> EvidenceRef | None:
    """The citation a knowledge-tool hit carries. A hit without a complete citation cannot be cited."""
    citation = _get(hit, "citation")
    if citation is None:
        return None
    parts = {name: str(_get(citation, name) or "").strip() for name in ("kind", "id", "file", "locator", "quote")}
    if not (parts["kind"] and parts["id"] and parts["file"] and parts["locator"]):
        return None
    return EvidenceRef(**parts)


def combined_locator(refs: list[EvidenceRef]) -> str:
    """One locator for a finding that rests on several rows of the same file."""
    by_file: dict[str, list[str]] = {}
    for ref in refs:
        by_file.setdefault(ref.file, []).append(ref.locator)
    parts = []
    for file, locators in by_file.items():
        sheets: dict[str, list[str]] = {}
        rest = []
        for locator in locators:
            match = re.fullmatch(r"sheet (.+), row (\d+)", locator)
            if match:
                sheets.setdefault(match.group(1), []).append(match.group(2))
            else:
                rest.append(locator)
        merged = [
            f"sheet {sheet}, row{'s' if len(rows) > 1 else ''} {', '.join(sorted(set(rows), key=int))}"
            for sheet, rows in sheets.items()
        ] + rest
        parts.append(f"{file}, {'; '.join(merged)}")
    return " | ".join(parts)


def pct_change(new: float, old: float) -> float | None:
    return None if not old else round((new - old) / old * 100, 1)


# ---------------------------------------------------------------- evidence in

def collect_evidence(
    vehicle_line: str | None,
    market: str | None,
    *,
    variant: str | None = None,
    status: str | None = None,
    option_terms: list[str] | None = None,
    year: int | None = None,
    option_limit: int = 25,
    tools: Any = None,
) -> dict[str, list[Any]]:
    """Read sales and option rows through the knowledge tools (never hand-written SQL).

    `tools` defaults to `app.knowledge.tools`; tests pass a fake with the same two functions.
    """
    if tools is None:
        from app.knowledge import tools  # imported late: it needs the database driver and .env
    line, market_code = scope_filter(vehicle_line), scope_filter(market)
    sales = list(tools.get_sales(line=line, market=market_code, year=year))
    options: list[Any] = []
    seen: set[str] = set()
    for term in option_terms or [None]:
        for hit in tools.get_options(line=line, variant=variant, status=status, text=term, limit=option_limit):
            ref = evidence_ref(hit)
            key = ref.id if ref else str(id(hit))
            if key not in seen:
                seen.add(key)
                options.append(hit)
    return {"sales": sales, "options": options}


def load_seed_evidence(path: Path) -> dict[str, list[Any]]:
    """Knowledge-tool hits saved as JSON (`dataclasses.asdict(Hit)` shape); avoids the database."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Seed evidence JSON must be an object with 'sales' and 'options' lists")
    return {"sales": list(payload.get("sales") or []), "options": list(payload.get("options") or [])}


def scope_seed_evidence(
    evidence: dict[str, list[Any]],
    vehicle_line: str | None,
    market: str | None,
    option_terms: list[str] | None = None,
) -> dict[str, list[Any]]:
    """Apply to seeded hits the filters the knowledge tools would have applied in SQL."""
    line, market_code = scope_filter(vehicle_line), scope_filter(market)
    terms = [t.lower() for t in option_terms or [] if t.strip()]

    def in_line(hit: Any) -> bool:
        return line is None or (_get(hit, "meta") or {}).get("vehicle_line") == line

    def matches(hit: Any) -> bool:
        if not terms:
            return True
        haystack = f"{_get(hit, 'text') or ''} {_get(_get(hit, 'citation') or {}, 'quote') or ''}".lower()
        return any(term in haystack for term in terms)

    return {
        "sales": [
            h for h in evidence.get("sales", [])
            if in_line(h) and (market_code is None or (_get(h, "meta") or {}).get("market_code") == market_code)
        ],
        "options": [h for h in evidence.get("options", []) if in_line(h) and matches(h)],
    }


def load_sales_portfolio_draft(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Sales & Portfolio Agent draft JSON must be an object")
    payload.setdefault("option_terms", [])
    return payload


def option_terms_from_draft(draft: dict[str, Any]) -> list[str]:
    """The model only proposes search terms. Findings come from the rows those terms retrieve."""
    terms: list[str] = []
    for value in draft.get("option_terms") or []:
        term = str(value).strip()
        if term and term.lower() not in {t.lower() for t in terms}:
            terms.append(term)
    return terms[:MAX_OPTION_TERMS]


def build_option_terms_prompt(vehicle_line: str, query: str) -> str:
    return f"""You help the Sales & Portfolio Agent of a vehicle requirements pipeline look up equipment options.

The option list is a German BMW sales catalog (vehicle line: {vehicle_line}). Option names are German,
for example "Sitzbelüftung", "Panorama-Glasdach", "Anhängerkupplung", "Driving Assistant Professional".

PM query: {query}

Return strict JSON: {{"option_terms": ["German substring to match option names", "..."]}}
- At most {MAX_OPTION_TERMS} short substrings, each likely to appear in an option name or description.
- Return an empty list if the query is not about specific equipment (then all options are read).
- Do not state facts, numbers, uptake or availability. Only search terms.
"""


def require_openai() -> Any:
    if OpenAI is None:
        raise RuntimeError("The OpenAI SDK is not installed. Run `pip install -e backend`.")
    return OpenAI


def require_psycopg() -> Any:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run `pip install -e backend`.")
    return psycopg


def propose_option_terms_with_openai(client: "OpenAIClient", vehicle_line: str, query: str) -> dict[str, Any]:
    response = client.responses.create(
        model=TERMS_MODEL,
        input=build_option_terms_prompt(vehicle_line, query),
        text={"format": {"type": "json_object"}},
    )
    return json.loads(response.output_text)


# ---------------------------------------------------------------- findings

def sales_findings(hits: list[Any], skipped: list[dict[str, str]]) -> list[SalesPortfolioFinding]:
    rows: list[tuple[dict[str, Any], EvidenceRef]] = []
    for hit in hits:
        ref = evidence_ref(hit)
        meta = _get(hit, "meta") or {}
        if ref is None:
            skipped.append({"source": "sales", "reason": "sales row without a citation; no finding produced"})
            continue
        try:
            row = {
                "vehicle_line": str(meta["vehicle_line"]),
                "market_code": str(meta["market_code"]),
                "year": int(meta["year"]),
                "volume": int(meta["volume"]),
                "is_forecast": bool(meta.get("is_forecast")),
            }
        except (KeyError, TypeError, ValueError):
            skipped.append({"source": f"{ref.file}, {ref.locator}", "reason": "sales row is missing line, market, year or volume"})
            continue
        rows.append((row, ref))

    findings: list[SalesPortfolioFinding] = []
    groups: dict[tuple[str, str], list[tuple[dict[str, Any], EvidenceRef]]] = {}
    for row, ref in rows:
        groups.setdefault((row["vehicle_line"], row["market_code"]), []).append((row, ref))

    def finding(line: str, market: str, text: str, refs: list[EvidenceRef], metrics: dict[str, Any],
                evidence_level: str, assumptions: list[str]) -> SalesPortfolioFinding:
        if line == "G68":
            assumptions = assumptions + ["G68 is taken to be the China row of the G60_G68 sales sheet (to confirm with BMW)."]
        return SalesPortfolioFinding(
            source_file=refs[0].file,
            locator=combined_locator(refs),
            text=text,
            signal_type="business_signal",
            evidence_level=evidence_level,
            market=market,
            vehicle_line=line,
            sentiment=None,
            sample_size=None,
            trust_tier=None,
            snapshot="\n".join(ref.quote for ref in refs),
            metrics=metrics,
            citations=refs,
            assumptions=assumptions,
        )

    for (line, market), group in sorted(groups.items()):
        group.sort(key=lambda item: item[0]["year"])
        actual = [item for item in group if not item[0]["is_forecast"]]
        forecast = [item for item in group if item[0]["is_forecast"]]
        latest = actual[-1] if actual else None
        if latest:
            row, ref = latest
            first_row, first_ref = actual[0]
            text = f"{line} {market}: {row['volume']:,} units sold in {row['year']}"
            refs = [ref]
            metrics: dict[str, Any] = {"metric": "sales_volume", "year": row["year"], "volume": row["volume"]}
            change = pct_change(row["volume"], first_row["volume"]) if first_row["year"] != row["year"] else None
            if change is not None:
                text += f", {change:+.1f}% vs {first_row['year']} ({first_row['volume']:,} units)"
                refs = [first_ref, ref]
                metrics |= {"base_year": first_row["year"], "base_volume": first_row["volume"], "change_pct": change}
            findings.append(finding(line, market, text + ".", refs, metrics, "Verified", []))
        for row, ref in forecast:
            text = f"{line} {market}: {row['volume']:,} units forecast for {row['year']}"
            refs = [ref]
            metrics = {"metric": "sales_forecast", "year": row["year"], "volume": row["volume"]}
            change = pct_change(row["volume"], latest[0]["volume"]) if latest else None
            if latest and change is not None:
                text += f", {change:+.1f}% vs {latest[0]['year']} actual ({latest[0]['volume']:,} units)"
                refs = [latest[1], ref]
                metrics |= {"base_year": latest[0]["year"], "base_volume": latest[0]["volume"], "change_pct": change}
            findings.append(finding(
                line, market, text + ".", refs, metrics, "Interpreted",
                [f"The {row['year']} volume is a forecast in the sales file, not an observed sale."],
            ))

    # Market mix per line, in the latest year that has observed volumes.
    by_line: dict[str, list[tuple[dict[str, Any], EvidenceRef]]] = {}
    for row, ref in rows:
        if not row["is_forecast"]:
            by_line.setdefault(row["vehicle_line"], []).append((row, ref))
    for line, items in sorted(by_line.items()):
        year = max(row["year"] for row, _ in items)
        in_year = sorted((item for item in items if item[0]["year"] == year), key=lambda item: -item[0]["volume"])
        total = sum(row["volume"] for row, _ in in_year)
        if len({row["market_code"] for row, _ in in_year}) < 2 or total <= 0:
            continue
        shares = {row["market_code"]: round(row["volume"] / total * 100, 1) for row, _ in in_year}
        mix = ", ".join(f"{row['market_code']} {shares[row['market_code']]:.1f}% ({row['volume']:,})" for row, _ in in_year)
        findings.append(finding(
            line, ALL, f"{line} volume mix by market in {year}: {mix} of {total:,} units.",
            [ref for _, ref in in_year],
            {"metric": "market_share_of_line_volume", "year": year, "total_volume": total, "share_pct": shares},
            "Verified",
            ["Shares are of the markets present in the sales file for this line, not of the total market."],
        ))
    return findings


def variant_statuses(availability: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per variant: `standard`, `optional`, or `conditional` (standard only on some price lines or under a
    condition such as a package). An option can have several price lines per variant."""
    lines: dict[str, list[dict[str, Any]]] = {}
    for entry in availability:
        if entry.get("variant") and entry.get("status") in {"standard", "optional"}:
            lines.setdefault(str(entry["variant"]), []).append(entry)
    result = {}
    for variant, entries in lines.items():
        statuses = {e["status"] for e in entries}
        if statuses == {"standard"} and not any(e.get("condition") for e in entries):
            status = "standard"
        elif "standard" in statuses:
            status = "conditional"
        else:
            status = "optional"
        result[variant] = {"status": status, "powertrain": entries[0].get("powertrain")}
    return result


def option_findings(hits: list[Any], scope_market: str | None, skipped: list[dict[str, str]]) -> list[SalesPortfolioFinding]:
    findings: list[SalesPortfolioFinding] = []
    for hit in hits:
        ref = evidence_ref(hit)
        meta = _get(hit, "meta") or {}
        if ref is None:
            skipped.append({"source": "options", "reason": "option row without a citation; no finding produced"})
            continue
        variants = variant_statuses(list(meta.get("availability") or []))
        if not variants:
            skipped.append({"source": f"{ref.file}, {ref.locator}", "reason": "option has no per-variant availability rows"})
            continue
        line = str(meta.get("vehicle_line") or ALL)
        name = str(_get(hit, "text") or ref.quote).strip()
        code = str(meta.get("code") or "").strip()

        names = {s: sorted(v for v, d in variants.items() if d["status"] == s) for s in ("standard", "optional", "conditional")}
        total = len(variants)
        n_standard, n_optional, n_conditional = (len(names[s]) for s in ("standard", "optional", "conditional"))
        share = round(n_standard / total * 100, 1)
        by_powertrain: dict[str, dict[str, int]] = {}
        for data in variants.values():
            counts = by_powertrain.setdefault(str(data["powertrain"] or "unknown"), {"standard": 0, "optional": 0, "conditional": 0})
            counts[data["status"]] += 1

        text = (
            f"{line} {'SA ' + code + ' ' if code else ''}\"{name}\": standard on {n_standard} of {total} "
            f"catalog variant{'s' if total != 1 else ''} ({share:.1f}%), optional on {n_optional}"
        )
        if n_conditional:
            text += f", standard only under a condition on {n_conditional}"
        text += "."
        if 0 < n_standard <= 4 and n_standard < total:
            text += f" Standard on: {', '.join(names['standard'])}."

        assumptions = [NO_TAKE_RATE, "Availability is from the German sales catalog; other markets may differ."]
        market_code = scope_filter(scope_market)
        if market_code and market_code != CATALOG_MARKET:
            assumptions.append(f"No {market_code} option list is in the data; the German catalog is used as a stand-in.")
        out_of_scope = OUT_OF_SCOPE_REASON if OUT_OF_SCOPE_RE.search(f"{name} {ref.quote} {meta.get('section') or ''}") else None

        findings.append(SalesPortfolioFinding(
            source_file=ref.file,
            locator=f"{ref.file}, {ref.locator}",
            text=text,
            signal_type="business_signal",
            evidence_level="Verified",
            market=CATALOG_MARKET,
            vehicle_line=line,
            sentiment=None,
            sample_size=total,
            trust_tier=None,
            snapshot=ref.quote,
            metrics={
                "metric": "standard_fitment_share",
                "option_code": code,
                "share_pct": share,
                "variants": total,
                "standard": n_standard,
                "optional": n_optional,
                "conditional": n_conditional,
                "standard_variants": names["standard"],
                "optional_variants": names["optional"],
                "conditional_variants": names["conditional"],
                "by_powertrain": by_powertrain,
            },
            citations=[ref],
            assumptions=assumptions,
            out_of_scope_reason=out_of_scope,
        ))
    return findings


def build_result(
    vehicle_line: str | None,
    market: str | None,
    query: str,
    evidence: dict[str, list[Any]],
    *,
    filters: dict[str, Any] | None = None,
) -> SalesPortfolioResult:
    """Turn knowledge-tool hits into cited findings. Deterministic: no model writes a claim or a number."""
    skipped: list[dict[str, str]] = []
    sales_hits = list(evidence.get("sales") or [])
    option_hits = list(evidence.get("options") or [])
    findings = sales_findings(sales_hits, skipped) + option_findings(option_hits, market, skipped)

    line_label, market_label = scope_label(vehicle_line), scope_label(market)
    applied = {"vehicle_line": line_label, "market": market_label} | {k: v for k, v in (filters or {}).items() if v not in (None, [], "")}
    files = {citation.file for f in findings for citation in f.citations}
    summary = summarize(line_label, market_label, query, applied, len(sales_hits), len(option_hits), sorted(files), findings, skipped)
    return SalesPortfolioResult(
        agent_name=AGENT_NAME,
        vehicle_line=line_label,
        market=market_label,
        query=query,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        sources_read=len(files),
        filters=applied,
        findings=findings,
        skipped=skipped,
        summary=summary,
    )


def summarize(
    vehicle_line: str,
    market: str,
    query: str,
    filters: dict[str, Any],
    sales_rows: int,
    option_rows: int,
    files: list[str],
    findings: list[SalesPortfolioFinding],
    skipped: list[dict[str, str]],
) -> str:
    in_scope = [f for f in findings if not f.out_of_scope_reason]
    out_of_scope = [f for f in findings if f.out_of_scope_reason]
    option_limit = filters.get("option_limit")
    lines = [
        f"{AGENT_NAME} looked at {sales_rows} sales row(s) and {option_rows} option row(s) for {vehicle_line} / {market}: {query}",
        "Filters: " + ", ".join(f"{k}={', '.join(v) if isinstance(v, list) else v}" for k, v in filters.items()),
        "Sources: " + (", ".join(files) if files else "none with a usable citation"),
        "",
        "Findings:",
    ]
    if in_scope:
        for finding in in_scope:
            lines.append(f"- {finding.text} ({finding.evidence_level}; {finding.locator})")
    else:
        lines.append("- No usable sales or portfolio findings were produced.")
    if out_of_scope:
        lines.extend(["", "Out-of-scope bin (not for requirements):"])
        for finding in out_of_scope:
            lines.append(f"- {finding.text} ({finding.out_of_scope_reason}; {finding.locator})")

    lines.extend(["", "Confidence and gaps:"])
    if any(f.evidence_level == "Verified" for f in findings):
        lines.append("- Volumes, shares and percentages are computed in code from the cited rows (deterministic, Verified).")
    if any(f.metrics.get("metric") == "standard_fitment_share" for f in findings):
        lines.append(f"- {NO_TAKE_RATE}")
        lines.append("- Option availability comes from the German catalogs only; list prices in them were not used (pricing is out of scope).")
    if any(f.metrics.get("metric") == "sales_forecast" for f in findings):
        lines.append("- Forecast volumes are the sales file's own projection and are marked Interpreted.")
    if sales_rows:
        lines.append("- Sales volumes are per line, market and year; they are not split by variant, powertrain or option.")
    else:
        lines.append("- No sales rows matched this scope.")
    if not option_rows:
        lines.append("- No option rows matched this scope and these search terms.")
    elif option_limit and option_rows >= int(option_limit):
        lines.append(f"- The option lookup stopped at its limit of {option_limit} per search term; more options may exist.")
    if skipped:
        lines.append(f"- {len(skipped)} row(s) were skipped because they had no citation or no usable values.")
    if not findings:
        lines.append("- The step needs a different scope or a narrower PM steering note.")
    lines.append("- Nothing was accepted, scored or prioritized; the step waits for PM review.")
    return "\n".join(lines)


# ---------------------------------------------------------------- storage

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
        "values (%s, %s, 1, 'awaiting_review', %s, %s, now(), "
        "(select coalesce(max(position), 0) + 1 from public.step where run_id = %s)) returning id",
        (run_id, AGENT_NAME, summary, AGENT_NAME, run_id),
    ).fetchone()[0]


EVIDENCE_COLUMN = {"sales": "sales_volume_id", "option": "option_id"}


def store_result(conn: Any, client: "OpenAIClient", result: SalesPortfolioResult, run_id: str | None, step_id: str | None) -> None:
    """Write findings with their evidence links and leave the step in `awaiting_review`."""
    with conn.transaction():
        stored_step_id = ensure_step(conn, run_id, step_id, result.summary)
        embeddings = client.embeddings.create(
            model=EMBED_MODEL,
            input=[finding.text[:MAX_EMBED_CHARS] for finding in result.findings] or ["empty"],
        ).data
        for finding, embedding in zip(result.findings, embeddings):
            source = conn.execute("select id from public.source where uri = %s", (finding.source_file,)).fetchone()
            if not source:
                continue  # the cited file is not a known source, so the finding cannot be stored
            source_id = source[0]
            dedupe = hashlib.sha256(f"{source_id}|{finding.locator}|{finding.text}".encode("utf-8")).hexdigest()
            exists = conn.execute(
                "select id from public.finding where source_id = %s and locator = %s and text = %s",
                (source_id, finding.locator, finding.text),
            ).fetchone()
            if exists:
                continue
            finding_id = conn.execute(
                "insert into public.finding (source_id, locator, text, signal_type, evidence_level, sentiment, sample_size, "
                "market, vehicle_line, out_of_scope_reason, extracted_by, step_id, embedding, source_snapshot, assumptions, "
                "dedupe_key) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::extensions.vector,%s,%s,%s) returning id",
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
                    finding.out_of_scope_reason,
                    AGENT_NAME,
                    stored_step_id,
                    vec(embedding.embedding),
                    finding.snapshot,
                    finding.assumptions,
                    dedupe,
                ),
            ).fetchone()[0]
            for citation in finding.citations:
                column = EVIDENCE_COLUMN.get(citation.kind)
                if column:
                    conn.execute(
                        f"insert into public.finding_evidence (finding_id, {column}, quote) values (%s, %s, %s)",
                        (finding_id, citation.id, citation.quote),
                    )
        if stored_step_id:
            refs = [{"type": "finding", "locator": f.locator, "source": f.source_file} for f in result.findings]
            conn.execute(
                "update public.step set structured_output_refs = %s::jsonb where id = %s",
                (json.dumps(refs), stored_step_id),
            )


# ---------------------------------------------------------------- entry points

def run(
    vehicle_line: str | None,
    market: str | None,
    query: str = "",
    *,
    variant: str | None = None,
    status: str | None = None,
    option_terms: list[str] | None = None,
    year: int | None = None,
    option_limit: int = 25,
    tools: Any = None,
) -> SalesPortfolioResult:
    """Read the scope through the knowledge tools and return cited findings. Writes nothing."""
    evidence = collect_evidence(
        vehicle_line, market, variant=variant, status=status, option_terms=option_terms, year=year,
        option_limit=option_limit, tools=tools,
    )
    filters = {"variant": variant, "status": status, "year": year, "option_terms": option_terms, "option_limit": option_limit}
    return build_result(vehicle_line, market, query, evidence, filters=filters)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Sales & Portfolio Agent")
    parser.add_argument("query", nargs="?", default="", help="PM research question or steering note")
    parser.add_argument("--vehicle-line", default=ALL, help="F70|G60|G68|G70, or ALL for no filter")
    parser.add_argument("--market", default=ALL, help="EU|CN|US|RoW, or ALL for no filter")
    parser.add_argument("--variant", help="catalog variant name, e.g. 530e")
    parser.add_argument("--status", choices=["standard", "optional"])
    parser.add_argument("--year", type=int)
    parser.add_argument("--option-text", action="append", help="German substring of an option name; repeatable")
    parser.add_argument("--max-options", type=int, default=25, help="option rows read per search term")
    parser.add_argument("--run-id")
    parser.add_argument("--step-id")
    parser.add_argument("--seed-evidence", type=Path, help="JSON of knowledge-tool hits; avoids the database")
    parser.add_argument("--draft-json", type=Path, help="JSON with option_terms; avoids the OpenAI term proposal")
    parser.add_argument("--dry-run", action="store_true", help="print JSON result instead of writing findings")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    terms = [t for t in args.option_text or [] if t.strip()]
    if not terms and args.draft_json:
        terms = option_terms_from_draft(load_sales_portfolio_draft(args.draft_json))
    elif not terms and args.query and not args.seed_evidence:
        terms = option_terms_from_draft(propose_option_terms_with_openai(require_openai()(), scope_label(args.vehicle_line), args.query))

    if args.seed_evidence:
        evidence = scope_seed_evidence(load_seed_evidence(args.seed_evidence), args.vehicle_line, args.market, terms)
        filters = {"variant": args.variant, "status": args.status, "year": args.year, "option_terms": terms}
        result = build_result(args.vehicle_line, args.market, args.query, evidence, filters=filters)
    else:
        result = run(
            args.vehicle_line, args.market, args.query, variant=args.variant, status=args.status,
            option_terms=terms, year=args.year, option_limit=args.max_options,
        )

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
