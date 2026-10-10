"""Check the Supabase connection and the state of the project database.

Usage (from the repo root):  python skills/database-setup/scripts/check_db.py [--openai]
Reads SUPABASE_DB_URL (and checks OPENAI_API_KEY is set) from .env. Never prints secrets.
--openai additionally makes one tiny embeddings call to prove the OpenAI key and model work and
that the vector size (1536) matches the database columns.
Exit code 0 = ready, 1 = something is missing.
"""
import os
import sys
from urllib.parse import urlparse

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

EXPECTED_TABLES = [
    "source", "feedback_raw", "chunk", "option", "option_availability", "sales_volume", "study_response",
    "ontology", "finding", "finding_evidence", "cluster", "requirement", "score",
    "pipeline_run", "step", "audit_event", "country_market", "model_variant",
    "design_decisions", "architecture_docs",
]
EXPECTED_FUNCTIONS = ["match_chunks", "match_feedback", "search_feedback", "search_docs"]
problems: list[str] = []


def ok(msg): print(f"  ok    {msg}")
def bad(msg): problems.append(msg); print(f"  FAIL  {msg}")


print("environment")
url = os.environ.get("SUPABASE_DB_URL")
if not url:
    bad("SUPABASE_DB_URL is not set in .env (see skills/database-setup/SKILL.md)")
    sys.exit(1)
u = urlparse(url)
ok(f"SUPABASE_DB_URL set -> host {u.hostname}, port {u.port}, user {u.username}")
if u.port == 6543:
    bad("port 6543 is the transaction pooler: use the session pooler (5432) or the direct connection")
if "[YOUR-PASSWORD]" in url:
    bad("the connection string still contains the [YOUR-PASSWORD] placeholder")
(ok if os.environ.get("OPENAI_API_KEY") else bad)("OPENAI_API_KEY " + ("set" if os.environ.get("OPENAI_API_KEY") else "missing (needed for embeddings and search)"))

print("connection")
try:
    conn = psycopg.connect(url, connect_timeout=10, autocommit=True)
except Exception as e:
    msg = str(e).strip().splitlines()[0]
    bad(f"cannot connect: {msg}")
    if "could not translate host" in msg or "No route" in msg or "Network is unreachable" in msg:
        print("        hint: the direct host is IPv6-only; use the session pooler string from Connect in the dashboard")
    if "password authentication failed" in msg:
        print("        hint: wrong password; reset it in Project Settings -> Database")
    sys.exit(1)
ok(f"connected as {conn.execute('select current_user').fetchone()[0]}")

print("extensions")
ext = {r[0] for r in conn.execute("select extname from pg_extension")}
(ok if "vector" in ext else bad)("pgvector " + ("enabled" if "vector" in ext else "not enabled (migration init_schema)"))

print("tables (rows)")
present = {r[0] for r in conn.execute("select table_name from information_schema.tables where table_schema='public'")}
for t in EXPECTED_TABLES:
    if t in present:
        ok(f"{t}: {conn.execute(f'select count(*) from public.{t}').fetchone()[0]}")
    else:
        bad(f"{t} missing (apply supabase/migrations/ in filename order)")

print("functions and indexes")
funcs = {r[0] for r in conn.execute("select proname from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='public'")}
for f in EXPECTED_FUNCTIONS:
    (ok if f in funcs else bad)(f"function {f}" + ("" if f in funcs else " missing"))
idx = {r[0] for r in conn.execute("select indexname from pg_indexes where schemaname='public'")}
for i in ("feedback_raw_embedding_idx", "chunk_embedding_idx"):
    (ok if i in idx else bad)(f"vector index {i}" + ("" if i in idx else " missing (rebuild: create index ... using hnsw (embedding extensions.vector_cosine_ops))"))

if "--openai" in sys.argv:
    print("openai")
    try:
        from openai import OpenAI
        v = OpenAI().embeddings.create(model="text-embedding-3-small", input="connection check").data[0].embedding
        (ok if len(v) == 1536 else bad)(f"text-embedding-3-small returned {len(v)} dimensions (database columns are 1536)")
    except Exception as e:
        bad(f"embeddings call failed: {type(e).__name__}: {str(e).strip().splitlines()[0][:120]}")

print()
print("READY" if not problems else f"{len(problems)} problem(s) found")
sys.exit(1 if problems else 0)
