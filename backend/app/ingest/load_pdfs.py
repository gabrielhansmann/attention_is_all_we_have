"""Chunk the catalog PDFs, embed with OpenAI, and load them into Supabase (source + chunk).

Usage:  python -m app.ingest.load_pdfs [--dry-run] [path/to/G60_OptionList.PDF ...]   (default: data/*_OptionList.PDF)
Needs OPENAI_API_KEY and SUPABASE_DB_URL in .env (use the direct or session-pooler URL).
Re-running replaces a file's existing chunks, so it is safe to repeat.
"""
import argparse
import os
from pathlib import Path

import psycopg
from app.config import DATA_DIR, load_env
from app.ingest.load_excel import source_id as register_source
from app.ingest.pdf_chunks import chunk_pdf
from openai import OpenAI

load_env()
EMBED_MODEL = "text-embedding-3-small"
BATCH = 100


def vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7f}" for x in v) + "]"


def embed_chunks(client, chunks) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for i in range(0, len(chunks), BATCH):
        batch = [c.embed_input for c in chunks[i:i + BATCH]]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        embeddings += [d.embedding for d in resp.data]
    return embeddings


def store_chunks(conn, name, vehicle_line, chunks, embeddings):
    """Register the file as a source and replace its chunks. Returns the source id."""
    with conn.transaction():
        source_id = register_source(conn, name, vehicle_line, type="internal_pdf", title=chunks[0].title)
        conn.execute("delete from public.chunk where source_id = %s", (source_id,))
        for c, e in zip(chunks, embeddings):
            conn.execute(
                "insert into public.chunk (source_id, locator, heading, content, embedding, page, chunk_index) "
                "values (%s, %s, %s, %s, %s::extensions.vector, %s, %s)",
                (source_id, c.locator, c.heading, c.text, vec(e), c.page, c.index),
            )
    return source_id


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dry-run", action="store_true", help="chunk and embed, but do not write to the database")
    args = ap.parse_args()
    files = [Path(f) for f in args.files] or sorted(DATA_DIR.glob("*_OptionList.PDF"))

    client = OpenAI()
    conn = None if args.dry_run else psycopg.connect(os.environ["SUPABASE_DB_URL"])

    for path in files:
        chunks = chunk_pdf(path)
        embeddings = embed_chunks(client, chunks)
        print(f"{path.name}: {len(chunks)} chunks embedded ({len(embeddings[0])} dims)")
        if conn is None:
            continue
        source_id = store_chunks(conn, path.name, path.name.split("_")[0], chunks, embeddings)
        print(f"  stored in Supabase as source {source_id}")


if __name__ == "__main__":
    main()
