"""Parse the equipment tables of the catalog PDFs and load them into option + option_availability.

Usage:  python -m app.ingest.load_options [path/to/G60_OptionList.PDF ...]   (default: data/*_OptionList.PDF)
Needs SUPABASE_DB_URL in .env and the PDFs already registered by load_pdfs.py (source rows).
Re-running replaces a file's options.
"""
import os
import sys
from pathlib import Path

import psycopg
from app.config import DATA_DIR, load_env
from app.ingest.pdf_options import parse_pdf

load_env()


def main() -> None:
    files = [Path(f) for f in sys.argv[1:]] or sorted(DATA_DIR.glob("*_OptionList.PDF"))
    conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True)
    for path in files:
        row = conn.execute("select id, vehicle_line from public.source where uri = %s", (path.name,)).fetchone()
        if not row:
            sys.exit(f"{path.name} is not registered yet: run `python -m app.ingest.load_pdfs` first")
        source_id, line = row
        options = parse_pdf(path)
        n_avail = 0
        with conn.transaction():
            conn.execute("delete from public.option where source_id = %s", (source_id,))
            for o in options:
                option_id = conn.execute(
                    "insert into public.option (source_id, vehicle_line, code, name, category, market, locator, "
                    "description, section, page) values (%s,%s,%s,%s,%s,'DE',%s,%s,%s,%s) returning id",
                    (source_id, line, o.code, o.name, o.section, f"p.{o.page}", o.description or None, o.section, o.page),
                ).fetchone()[0]
                for i, e in enumerate(o.entries):
                    for variant, status in zip(e.variants, e.status):
                        conn.execute(
                            "insert into public.option_availability (option_id, entry_no, variant, status, price_gross, "
                            "price_net, condition, inherited) values (%s,%s,%s,%s,%s,%s,%s,%s) "
                            "on conflict (option_id, entry_no, variant) do nothing",
                            (option_id, i, variant, status, e.price_gross, e.price_net, e.condition, e.inherited),
                        )
                        n_avail += 1
        print(f"{path.name}: {len(options)} options, {n_avail} availability rows")


if __name__ == "__main__":
    main()
