"""Retrieval tools over the knowledge layer. Every hit carries a Citation (file + locator + quote)
resolved from the stored row, so an agent can only cite what it actually retrieved.

Semantic + keyword search:  search_feedback, search_docs
Exact lookups:              get_options, get_sales, get_study
Counting:                   feedback_stats, feedback_rows
Citations:                  cite

Needs OPENAI_API_KEY and SUPABASE_DB_URL in .env.   Demo:  python -m knowledge.tools
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from psycopg.rows import dict_row

load_dotenv(".env")
EMBED_MODEL = "text-embedding-3-small"
QUOTE_CHARS = 300


@dataclass
class Citation:
    kind: str          # feedback | pdf_text | option | study | sales
    id: str
    file: str
    locator: str       # e.g. "sheet Feedback_Explorer, row 4642 (G60-3695)" or "page 14"
    quote: str

    def __str__(self) -> str:
        return f'{self.file}, {self.locator}: "{self.quote}"'


@dataclass
class Hit:
    citation: Citation
    text: str
    meta: dict = field(default_factory=dict)
    score: float | None = None


@lru_cache(maxsize=1)
def _conn() -> psycopg.Connection:
    return psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True, row_factory=dict_row)


@lru_cache(maxsize=1)
def _openai() -> OpenAI:
    return OpenAI()


def _embed(text: str) -> str:
    v = _openai().embeddings.create(model=EMBED_MODEL, input=text).data[0].embedding
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def _quote(text: str) -> str:
    return " ".join(text.split())[:QUOTE_CHARS]


def resolve_domain(name: str | None) -> str | None:
    """Top-level ontology domain id from its key ('usability') or label ('Comfort & Space')."""
    if not name:
        return None
    row = _conn().execute(
        "select id from public.ontology where kind='domain' and parent_id is null "
        "and (key = %s or label ilike %s) limit 1", (name.lower(), name + "%")).fetchone()
    if not row:
        raise ValueError(f"unknown domain: {name}")
    return str(row["id"])


# ---------------------------------------------------------------- semantic + keyword search

def search_feedback(query: str, *, line: str | None = None, market: str | None = None,
                    domain: str | None = None, polarity: str | None = None,
                    powertrain: str | None = None, k: int = 10) -> list[Hit]:
    """Customer comments, hybrid vector + keyword search, filtered by normalized fields.
    line: F70|G60|G68|G70, market: EU|CN|US|RoW, polarity: positive|negative|request,
    powertrain: ICE|PHEV|BEV, domain: top-level ontology domain key or label."""
    rows = _conn().execute(
        "select * from public.search_feedback(%s::extensions.vector, %s, %s, %s, %s, %s::uuid, %s, %s)",
        (_embed(query), query, k, line, market, resolve_domain(domain), polarity, powertrain)).fetchall()
    return [Hit(
        Citation("feedback", str(r["id"]), r["file"], f"sheet {r['sheet']}, row {r['row_no']} ({r['ext_id']})",
                 _quote(r["comment"])),
        r["comment"],
        {k_: r[k_] for k_ in ("vehicle_line", "market_code", "country", "powertrain", "feedback_type",
                              "polarity", "domain", "similarity")},
        r["score"]) for r in rows]


def search_docs(query: str, *, line: str | None = None, k: int = 8) -> list[Hit]:
    """Catalog PDF text (German), hybrid search. Cite by file + page."""
    rows = _conn().execute(
        "select * from public.search_docs(%s::extensions.vector, %s, %s, %s)",
        (_embed(query), query, k, line)).fetchall()
    return [Hit(
        Citation("pdf_text", str(r["id"]), r["file"], f"page {r['page']}", _quote(r["content"])),
        r["content"],
        {"title": r["title"], "vehicle_line": r["vehicle_line"], "heading": r["heading"],
         "similarity": r["similarity"]},
        r["score"]) for r in rows]


# ---------------------------------------------------------------- exact lookups

def get_options(*, line: str | None = None, variant: str | None = None, status: str | None = None,
                text: str | None = None, limit: int = 25) -> list[Hit]:
    """Equipment options with per-variant availability. status: standard|optional.
    text matches the option name/description (case-insensitive, German)."""
    rows = _conn().execute(
        "select o.id, o.vehicle_line, o.code, o.name, o.description, o.section, o.page, s.uri, "
        "  json_agg(json_build_object('variant', v.name, 'powertrain', v.powertrain, 'status', a.status, "
        "    'price_gross', a.price_gross, 'condition', a.condition) order by a.entry_no, v.name) as availability "
        "from public.option o join public.source s on s.id = o.source_id "
        "join public.option_availability a on a.option_id = o.id join public.model_variant v on v.id = a.variant_id "
        "where (%(line)s::text is null or o.vehicle_line = %(line)s) "
        "  and (%(text)s::text is null or o.name ilike '%%' || %(text)s || '%%' or o.description ilike '%%' || %(text)s || '%%') "
        "  and (%(variant)s::text is null or v.name = %(variant)s) "
        "  and (%(status)s::text is null or a.status = %(status)s) "
        "group by o.id, s.uri order by o.vehicle_line, o.page, o.code limit %(limit)s",
        {"line": line, "variant": variant, "status": status, "text": text, "limit": limit}).fetchall()
    return [Hit(
        Citation("option", str(r["id"]), r["uri"], f"page {r['page']}, SA {r['code']}",
                 _quote(r["name"] + (" — " + r["description"] if r["description"] else ""))),
        r["name"], {"vehicle_line": r["vehicle_line"], "code": r["code"], "section": r["section"],
                    "availability": r["availability"]}) for r in rows]


def get_sales(*, line: str | None = None, market: str | None = None, year: int | None = None) -> list[Hit]:
    """Sales volumes by line, market and year (2030 is a forecast). Market codes EU|CN|US|RoW."""
    rows = _conn().execute(
        "select v.id, v.vehicle_line, v.market, v.market_code, v.year, v.volume, v.is_forecast, v.sheet, v.row_no, s.uri "
        "from public.sales_volume v join public.source s on s.id = v.source_id "
        "where (%(l)s::text is null or v.vehicle_line = %(l)s) and (%(m)s::text is null or v.market_code = %(m)s) "
        "and (%(y)s::int is null or v.year = %(y)s) order by v.vehicle_line, v.market_code, v.year",
        {"l": line, "m": market, "y": year}).fetchall()
    return [Hit(
        Citation("sales", str(r["id"]), r["uri"], f"sheet {r['sheet']}, row {r['row_no']}",
                 f"{r['vehicle_line']} {r['market']} {r['year']}: {r['volume']} units"
                 + (" (forecast)" if r["is_forecast"] else "")),
        f"{r['volume']}", {k_: r[k_] for k_ in ("vehicle_line", "market_code", "year", "volume", "is_forecast")})
        for r in rows]


def get_study(*, line: str | None = None, market: str | None = None, question: str | None = None,
              limit: int = 60) -> list[Hit]:
    """Customer-study results: mean ratings (EU/CN) or answer shares (US). question matches by substring."""
    rows = _conn().execute(
        "select r.id, r.vehicle_line, r.market_code, r.model, r.question, r.metric, r.answer_option, r.value, "
        "r.sheet, r.cell_ref, s.uri from public.study_response r join public.source s on s.id = r.source_id "
        "where (%(l)s::text is null or r.vehicle_line = %(l)s) and (%(m)s::text is null or r.market_code = %(m)s) "
        "and (%(q)s::text is null or r.question ilike '%%' || %(q)s || '%%') "
        "order by r.question, r.market_code, r.model, r.answer_option limit %(n)s",
        {"l": line, "m": market, "q": question, "n": limit}).fetchall()
    return [Hit(
        Citation("study", str(r["id"]), r["uri"], f"sheet {r['sheet']}, cell {r['cell_ref']}",
                 f"{r['question']} | {r['model']} | {(r['answer_option'] + ' ') if r['answer_option'] else ''}"
                 f"{r['metric']} = {float(r['value']):.3f}"),
        r["question"], {k_: r[k_] for k_ in ("vehicle_line", "market_code", "model", "metric", "answer_option")}
        | {"value": float(r["value"])}) for r in rows]


# ---------------------------------------------------------------- counting

_GROUPS = {"vehicle_line": "f.vehicle_line", "market_code": "f.market_code", "country": "f.country",
           "powertrain": "f.powertrain", "polarity": "f.polarity", "feedback_type": "f.feedback_type",
           "domain": "coalesce(p.label, 'unmapped')"}


def feedback_stats(group_by: str, *, line: str | None = None, market: str | None = None,
                   domain: str | None = None, polarity: str | None = None,
                   powertrain: str | None = None) -> list[dict]:
    """Comment counts grouped by one field, under optional filters. Counts are exact (SQL), not sampled."""
    if group_by not in _GROUPS:
        raise ValueError(f"group_by must be one of {sorted(_GROUPS)}")
    return _conn().execute(
        f"select {_GROUPS[group_by]} as key, count(*) as n from public.feedback_raw f "
        "left join public.ontology c on c.id = f.domain_id left join public.ontology p on p.id = coalesce(c.parent_id, c.id) "
        "where (%(l)s::text is null or f.vehicle_line = %(l)s) and (%(m)s::text is null or f.market_code = %(m)s) "
        "and (%(d)s::uuid is null or p.id = %(d)s) and (%(po)s::text is null or f.polarity = %(po)s) "
        "and (%(pt)s::text is null or f.powertrain = %(pt)s) group by 1 order by 2 desc",
        {"l": line, "m": market, "d": resolve_domain(domain), "po": polarity, "pt": powertrain}).fetchall()


def feedback_rows(*, line: str | None = None, market: str | None = None, domain: str | None = None,
                  polarity: str | None = None, powertrain: str | None = None, limit: int = 20,
                  offset: int = 0) -> list[Hit]:
    """The concrete comments behind a count, for linking a finding to its evidence rows."""
    rows = _conn().execute(
        "select f.id, f.comment, f.sheet, f.row_no, f.ext_id, f.vehicle_line, f.market_code, f.polarity, "
        "f.powertrain, s.uri from public.feedback_raw f join public.source s on s.id = f.source_id "
        "left join public.ontology c on c.id = f.domain_id left join public.ontology p on p.id = coalesce(c.parent_id, c.id) "
        "where (%(l)s::text is null or f.vehicle_line = %(l)s) and (%(m)s::text is null or f.market_code = %(m)s) "
        "and (%(d)s::uuid is null or p.id = %(d)s) and (%(po)s::text is null or f.polarity = %(po)s) "
        "and (%(pt)s::text is null or f.powertrain = %(pt)s) order by f.row_no limit %(n)s offset %(o)s",
        {"l": line, "m": market, "d": resolve_domain(domain), "po": polarity, "pt": powertrain,
         "n": limit, "o": offset}).fetchall()
    return [Hit(Citation("feedback", str(r["id"]), r["uri"], f"sheet {r['sheet']}, row {r['row_no']} ({r['ext_id']})",
                         _quote(r["comment"])), r["comment"],
                {k_: r[k_] for k_ in ("vehicle_line", "market_code", "polarity", "powertrain")}) for r in rows]


# ---------------------------------------------------------------- citations

def cite(kind: str, id: str) -> Citation:
    """Resolve any stored evidence row to its citation; raises if it does not exist."""
    r = _conn().execute("select kind, id, file, locator, text from public.evidence_item where kind = %s and id = %s",
                        (kind, id)).fetchone()
    if not r:
        raise LookupError(f"no {kind} evidence with id {id}")
    return Citation(r["kind"], str(r["id"]), r["file"], r["locator"], _quote(r["text"]))


if __name__ == "__main__":
    print("== feedback_stats: G60 negative comments by market")
    for r in feedback_stats("market_code", line="G60", polarity="negative"):
        print("  ", r)
    print("== search_feedback: 'seat ventilation too weak', G60, negative")
    for h in search_feedback("seat ventilation too weak", line="G60", polarity="negative", k=3):
        print("  ", h.citation)
    print("== get_options: G60 wheels standard on 530e")
    for h in get_options(line="G60", text="Leichtmetallräder", variant="530e", status="standard", limit=3):
        print("  ", h.citation)
    print("== get_sales: G60 EU")
    for h in get_sales(line="G60", market="EU"):
        print("  ", h.citation)
