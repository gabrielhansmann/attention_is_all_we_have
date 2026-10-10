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
        "  (select count(*) from public.sales_volume v where v.source_id = s.id) as sales_rows "
        "from public.source s order by s.uri").fetchall()
    out = []
    for r in rows:
        counts = {k: r.pop(k) for k in ("feedback", "pdf_chunks", "options", "study_cells", "sales_rows")}
        r["counts"] = counts
        r["family"] = (
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
