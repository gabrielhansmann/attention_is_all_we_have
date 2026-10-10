"""Ask a question about the catalog PDFs and get an answer with real citations.

Usage:  python ingest/ask_pdf.py "Welche Felgen gibt es für den 5er?" [--line G60] [-k 8]
Needs OPENAI_API_KEY and SUPABASE_DB_URL in .env.
Citations are built from the retrieved chunks (file, page, verbatim text), never from model output.
"""
import argparse
import os
import re

import psycopg
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini")

SYSTEM = (
    "You answer questions about BMW catalog PDFs using ONLY the numbered excerpts provided. "
    "Cite every statement with its excerpt number like [2]. If the excerpts do not contain the "
    "answer, say so plainly. Answer in the language of the question. The excerpts are flattened "
    "table text: a ■/□ mark cannot be reliably tied to a model column, so never state which model "
    "variant has an option as standard or optional; say that the table needs checking in the PDF."
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--line", help="restrict to a vehicle line, e.g. G60")
    ap.add_argument("-k", type=int, default=8)
    args = ap.parse_args()

    client = OpenAI()
    q = client.embeddings.create(model=EMBED_MODEL, input=args.question).data[0].embedding
    qv = "[" + ",".join(f"{x:.7f}" for x in q) + "]"
    with psycopg.connect(os.environ["SUPABASE_DB_URL"]) as conn:
        rows = conn.execute(
            "select file, title, page, heading, content, similarity "
            "from public.match_chunks(%s::extensions.vector, %s, %s)",
            (qv, args.k, args.line),
        ).fetchall()
    if not rows:
        print("No chunks found. Have the PDFs been loaded?")
        return

    context = "\n\n".join(
        f"[{i}] {title}, Seite {page}" + (f", {heading}" if heading else "") + f"\n{content}"
        for i, (file, title, page, heading, content, _) in enumerate(rows, 1)
    )
    answer = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Excerpts:\n{context}\n\nQuestion: {args.question}"},
        ],
        temperature=0,
    ).choices[0].message.content
    print(answer, "\n")

    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", answer) if 1 <= int(n) <= len(rows)})
    print("Quellen / Sources:")
    for n in cited:
        file, title, page, heading, content, sim = rows[n - 1]
        quote = " ".join(content.split())[:300]
        print(f"[{n}] {file}, page {page}" + (f" ({heading})" if heading else "") + f"  [similarity {sim:.2f}]")
        print(f'    "{quote}"')


if __name__ == "__main__":
    main()
