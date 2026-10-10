"""Read-only views for the evidence library: which sources are loaded (files and web pages), what they cover,
which websites the web agents read, and where the evidence is thin.

All SQL lives in the backend; the frontend only calls /api/sources... and /api/evidence/coverage.
"""
from __future__ import annotations

from app.knowledge import tools


def list_sources() -> list[dict]:
    """Every registered source file with what was loaded from it (row counts per evidence kind)."""
    rows = tools._conn().execute(
        "select s.id, s.uri as file, s.type, s.vehicle_line, s.market, s.title, s.retrieved_at, s.trust_tier, "
        "  (select count(*) from public.feedback_raw f where f.source_id = s.id) as feedback, "
        "  (select count(*) from public.chunk c where c.source_id = s.id) as pdf_chunks, "
        "  (select count(*) from public.option o where o.source_id = s.id) as options, "
        "  (select count(*) from public.study_response r where r.source_id = s.id) as study_cells, "
        "  (select count(*) from public.sales_volume v where v.source_id = s.id) as sales_rows "
        "from public.source s order by (s.type = 'web'), s.uri").fetchall()
    out = []
    for r in rows:
        counts = {k: r.pop(k) for k in ("feedback", "pdf_chunks", "options", "study_cells", "sales_rows")}
        r["counts"] = counts
        r["family"] = (
            "Website" if r["type"] == "web" else
            "Customer feedback" if counts["feedback"] else
            "Product catalog" if counts["pdf_chunks"] or counts["options"] else
            "Customer study" if counts["study_cells"] else
            "Sales volumes" if counts["sales_rows"] else "Other")
        out.append(r)
    return out


def coverage() -> dict:
    """Evidence per vehicle line and market: customer comments, customer-study cells, 2025 sales volume.
    A zero is a real gap (for example there is no customer feedback for China); null sales means no row at all."""
    c = tools._conn()
    cells = c.execute(
        "select l.key as line, m.key as market, "
        "  (select count(*) from public.feedback_raw f where f.vehicle_line = l.key and f.market_code = m.key) as feedback, "
        "  (select count(*) from public.study_response r where r.vehicle_line = l.key and r.market_code = m.key) as study_cells, "
        "  (select sum(v.volume) from public.sales_volume v where v.vehicle_line = l.key and v.market_code = m.key and v.year = 2025) as sales_2025 "
        "from (select key from public.ontology where kind = 'vehicle_line' and active) l "
        "cross join (select key from public.ontology where kind = 'market' and active) m "
        "order by l.key, m.key").fetchall()
    options = {r["vehicle_line"]: r["n"] for r in c.execute(
        "select vehicle_line, count(*) as n from public.option group by 1")}
    return {"cells": [{**r, "sales_2025": int(r["sales_2025"]) if r["sales_2025"] is not None else None} for r in cells],
            "options_by_line": options,
            "total_feedback": c.execute("select count(*) as n from public.feedback_raw").fetchone()["n"]}


def source_graph() -> dict:
    """What each source covers, for the graph view: one link per source, vehicle line and market with the number
    of rows behind it. A null line or market means the rows are not tied to one (a catalog has no market)."""
    links = tools._conn().execute(
        "select source_id, vehicle_line as line, market_code as market, count(*) as rows "
        "  from public.feedback_raw group by 1, 2, 3 "
        "union all select source_id, vehicle_line, market_code, count(*) from public.study_response group by 1, 2, 3 "
        "union all select source_id, vehicle_line, market_code, count(*) from public.sales_volume group by 1, 2, 3 "
        "union all select s.id, s.vehicle_line, s.market, "
        "    (select count(*) from public.chunk c where c.source_id = s.id) "
        "    + (select count(*) from public.option o where o.source_id = s.id) "
        "  from public.source s where s.type in ('internal_pdf', 'web')").fetchall()
    return {"links": [{**l, "source_id": str(l["source_id"])} for l in links if l["rows"]]}


WEB_AGENTS = ("Market & Trend Agent", "Competitor Agent")
_HTTP = ("http://", "https://")


def web_research(limit: int = 300) -> list[dict]:
    """Websites the web agents read during runs, newest first, one entry per address.

    Read from the stored step outputs: a finding's `source_url` is a page the agent cited, an entry in
    `skipped` a page it read and did not use. `source_id` is set when the page is also a stored source."""
    c = tools._conn()
    steps = c.execute(
        "select s.agent_name, coalesce(s.resolved_at, s.launched_at) as at, s.structured_output_refs -> 'output' as output, "
        "  r.vehicle_line, r.market, r.query_text, r.conversation_id, v.title as conversation "
        "from public.step s join public.pipeline_run r on r.id = s.run_id "
        "left join public.conversation v on v.id = r.conversation_id "
        "where s.agent_name = any(%s) and s.structured_output_refs ? 'output' "
        "order by coalesce(s.resolved_at, s.launched_at) desc nulls last limit %s", (list(WEB_AGENTS), limit)).fetchall()
    stored = {r["uri"]: str(r["id"]) for r in c.execute("select id, uri from public.source where type = 'web'")}
    sites: dict[str, dict] = {}

    def site(url: str, step: dict) -> dict:
        scope = lambda v: None if v in (None, "", "ALL") else v
        return sites.setdefault(url, {
            "url": url, "domain": url.split("/")[2].removeprefix("www."), "title": None, "trust_tier": None,
            "findings": 0, "skipped_reason": None, "agent": step["agent_name"], "retrieved_at": step["at"],
            "vehicle_line": scope(step["vehicle_line"]), "market": scope(step["market"]), "request": step["query_text"],
            "conversation_id": str(step["conversation_id"]) if step["conversation_id"] else None,
            "conversation": step["conversation"], "source_id": stored.get(url)})

    for step in steps:
        output = step["output"] if isinstance(step["output"], dict) else {}
        for f in output.get("findings") or []:
            url = f.get("source_url") if isinstance(f, dict) else None
            if isinstance(url, str) and url.startswith(_HTTP):
                entry = site(url, step)
                entry["findings"] += 1
                entry["title"] = entry["title"] or f.get("title")
                entry["trust_tier"] = entry["trust_tier"] or f.get("trust_tier")
        for k in output.get("skipped") or []:
            url = k.get("source") if isinstance(k, dict) else None
            if isinstance(url, str) and url.startswith(_HTTP):
                entry = site(url, step)
                entry["skipped_reason"] = entry["skipped_reason"] or k.get("reason")
    return list(sites.values())


# ---------------------------------------------------------------- source viewer

_PAGE = __import__("re").compile(r"\bpage (\d+)")
NEIGHBOURS = 2   # feedback rows shown before and after the cited one


def evidence_context(kind: str, evidence_id: str) -> dict:
    """The cited passage in its surroundings, plus where the original file is, for the source viewer.

    `passages` are verbatim stored text in reading order; the cited one has `cited: true`. For a catalog
    page that is every chunk on the page, for a customer comment the rows around it in the sheet.
    Raises LookupError for an unknown id."""
    c = tools._conn()
    item = c.execute("select kind, id, file, locator, text, vehicle_line, market_code from public.evidence_item "
                     "where kind = %s and id = %s", (kind, evidence_id)).fetchone()
    if not item:
        raise LookupError(f"no {kind} evidence with id {evidence_id}")
    src = c.execute("select id, type, title from public.source where uri = %s", (item["file"],)).fetchone()
    passages = [{"id": str(item["id"]), "label": item["locator"], "text": item["text"], "cited": True}]
    page = None
    web = bool(src) and src["type"] == "web"
    if kind == "pdf_text" and src:
        page = int(_PAGE.search(item["locator"]).group(1))
        # A catalog page holds several chunks; a web page is stored one passage per number, so show its neighbours.
        rows = c.execute("select id, heading, content from public.chunk where source_id = %s and page between %s and %s "
                         "order by page, chunk_index", (src["id"], page - web, page + web)).fetchall()
        passages = [{"id": str(r["id"]), "label": r["heading"], "text": r["content"],
                     "cited": str(r["id"]) == str(item["id"])} for r in rows] or passages
    elif kind == "feedback" and src:
        row = c.execute("select sheet, row_no from public.feedback_raw where id = %s", (evidence_id,)).fetchone()
        rows = c.execute("select id, row_no, ext_id, comment from public.feedback_raw where source_id = %s "
                         "and sheet = %s and row_no between %s and %s and comment is not null order by row_no",
                         (src["id"], row["sheet"], row["row_no"] - NEIGHBOURS, row["row_no"] + NEIGHBOURS)).fetchall()
        passages = [{"id": str(r["id"]), "label": f"row {r['row_no']} ({r['ext_id']})", "text": r["comment"],
                     "cited": str(r["id"]) == str(item["id"])} for r in rows] or passages
    return {
        "kind": kind, "id": str(item["id"]), "file": item["file"], "locator": item["locator"],
        "title": src["title"] if src else None, "page": page, "passages": passages,
        "vehicle_line": item["vehicle_line"], "market_code": item["market_code"],
        "document": {"source_id": str(src["id"]), "type": src["type"], "openable": _file_path(item["file"]) is not None,
                     "url": item["file"] if web else None}
        if src else None,
    }


def _file_path(name: str):
    """The provided file inside data/, or None. Only plain file names are served, never a path."""
    from app.config import DATA_DIR
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    path = DATA_DIR / name
    return path if path.is_file() else None


def source_file(source_id: str):
    """(path, download name) of a registered source file that exists in data/, else raises LookupError."""
    row = tools._conn().execute("select uri from public.source where id = %s", (source_id,)).fetchone()
    path = _file_path(row["uri"]) if row else None
    if path is None:
        raise LookupError("source file is not available")
    return path, row["uri"]
