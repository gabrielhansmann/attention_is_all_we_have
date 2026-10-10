"""Chunk the catalog PDFs, embed with OpenAI, and load them into Supabase (source + chunk).

Usage:  python ingest/load_pdfs.py [--dry-run] [data/G60_OptionList.PDF ...]
Needs OPENAI_API_KEY and SUPABASE_DB_URL in .env (use the direct or session-pooler URL).
Re-running replaces a file's existing chunks, so it is safe to repeat.
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from pdf_chunks import chunk_pdf  # noqa: E402

load_dotenv()
EMBED_MODEL = "text-embedding-3-small"
BATCH = 100


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dry-run", action="store_true", help="chunk and embed, but do not write to the database")
    args = ap.parse_args()
    files = [Path(f) for f in args.files] or sorted(Path("data").glob("*_OptionList.PDF"))

    client = OpenAI()
    conn = None if args.dry_run else psycopg.connect(os.environ["SUPABASE_DB_URL"])

    for path in files:
        vehicle_line = path.name.split("_")[0]
        chunks = chunk_pdf(path)
        embeddings: list[list[float]] = []
        for i in range(0, len(chunks), BATCH):
            batch = [c.embed_input for c in chunks[i:i + BATCH]]
            resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
            embeddings += [d.embedding for d in resp.data]
        print(f"{path.name}: {len(chunks)} chunks embedded ({len(embeddings[0])} dims)")
        if conn is None:
            continue

        with conn.transaction():
            row = conn.execute("select id from public.source where uri = %s", (path.name,)).fetchone()
            if row:
                source_id = row[0]
                conn.execute("delete from public.chunk where source_id = %s", (source_id,))
            else:
                source_id = conn.execute(
                    "insert into public.source (type, uri, vehicle_line, title) values ('internal_pdf', %s, %s, %s) returning id",
                    (path.name, vehicle_line, chunks[0].title),
                ).fetchone()[0]
            for c, e in zip(chunks, embeddings):
                conn.execute(
                    "insert into public.chunk (source_id, locator, heading, content, embedding, page, chunk_index) "
                    "values (%s, %s, %s, %s, %s::extensions.vector, %s, %s)",
                    (source_id, c.locator, c.heading, c.text, vec(e), c.page, c.index),
                )
        print(f"  stored in Supabase as source {source_id}")


if __name__ == "__main__":
    main()
