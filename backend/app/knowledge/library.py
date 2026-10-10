"""Read-only views for the evidence library: which source files are loaded and where the evidence is thin.

All SQL lives in the backend; the frontend only calls /api/sources and /api/evidence/coverage.
"""
from __future__ import annotations

from app.knowledge import tools


def list_sources() -> list[dict]:
    """Every registered source file with what was loaded from it (row counts per evidence kind)."""
    rows = tools._conn().execute(
        "select s.id, s.uri as file, s.type, s.vehicle_line, s.market, s.title, s.retrieved_at, "
        "  (select count(*) from public.feedback_raw f where f.source_id = s.id) as feedback, "
        "  (select count(*) from public.chunk c where c.source_id = s.id) as pdf_chunks, "
        "  (select count(*) from public.option o where o.source_id = s.id) as options, "
        "  (select count(*) from public.study_response r where r.source_id = s.id) as study_cells, "
        "  (select count(*) from public.sales_volume v where v.source_id = s.id) as sales_rows, "
        "  (select count(*) from public.finding f where f.source_id = s.id) as findings "
        "from public.source s order by s.uri").fetchall()
    out = []
    for r in rows:
        counts = {k: r.pop(k) for k in ("feedback", "pdf_chunks", "options", "study_cells", "sales_rows", "findings")}
        r["counts"] = counts
        r["family"] = (
            "Customer feedback" if counts["feedback"] else
            "Product catalog" if counts["pdf_chunks"] or counts["options"] else
            "Customer study" if counts["study_cells"] else
            "Sales volumes" if counts["sales_rows"] else "Web research" if r["type"] == "web" else "Other")
        out.append(r)
    return out


def coverage() -> dict:
    """Evidence per vehicle line and market, using the newest recorded non-forecast sales year.
    Zero counts are real gaps; null sales means no row for that scope and year."""
    c = tools._conn()
    year = c.execute("select max(year) as year from public.sales_volume where not is_forecast").fetchone()["year"]
    cells = c.execute(
        "select l.key as line, m.key as market, "
        "  (select count(*) from public.feedback_raw f where f.vehicle_line = l.key and f.market_code = m.key) as feedback, "
        "  (select count(*) from public.study_response r where r.vehicle_line = l.key and r.market_code = m.key) as study_cells, "
        "  (select sum(v.volume) from public.sales_volume v where v.vehicle_line = l.key and v.market_code = m.key and v.year = %s and not v.is_forecast) as sales_volume "
        "from (select key from public.ontology where kind = 'vehicle_line' and active) l "
        "cross join (select key from public.ontology where kind = 'market' and active) m "
        "order by l.key, m.key", (year,)).fetchall()
    options = {r["vehicle_line"]: r["n"] for r in c.execute(
        "select vehicle_line, count(*) as n from public.option group by 1")}
    return {"sales_year": year, "cells": [{**r, "sales_volume": int(r["sales_volume"]) if r["sales_volume"] is not None else None} for r in cells],
            "options_by_line": options,
            "total_feedback": c.execute("select count(*) as n from public.feedback_raw").fetchone()["n"]}
