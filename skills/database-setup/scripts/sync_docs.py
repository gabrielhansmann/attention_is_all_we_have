"""Mirror docs/decisions/*.md and docs/architecture/*.md into Supabase (design_decisions, architecture_docs).

Usage (repo root, AFTER the push, on the pushed commit):
  python skills/database-setup/scripts/sync_docs.py [--dry-run]

Git is the source of truth; Supabase is a mirror. Upserts by id/path and records the current commit
sha. Run it from a checkout that contains the docs you just pushed: it never deletes rows, but it
would overwrite a mirrored doc with an older local version.
Reads SUPABASE_DB_URL from .env. Never prints secrets.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")
dry = "--dry-run" in sys.argv
sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
title = lambda s: (re.search(r"^#\s+(.+)$", s, re.M) or [None, None])[1]
status = lambda s: (re.search(r"Status:\s*`?([a-z]+)`?", s) or [None, None])[1]

decisions = sorted(Path("docs/decisions").glob("0*.md"))
architecture = sorted(Path("docs/architecture").glob("*.md"))
if dry:
    print(f"dry run: would upsert {len(decisions)} decisions and {len(architecture)} architecture docs at {sha[:7]}")
    sys.exit(0)

conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], autocommit=True)
with conn.transaction():
    for p in decisions:
        s = p.read_text()
        conn.execute(
            "insert into design_decisions (id, title, status, body, source_path, commit_sha, updated_at) "
            "values (%s,%s,%s,%s,%s,%s,now()) on conflict (id) do update set title=excluded.title, "
            "status=excluded.status, body=excluded.body, source_path=excluded.source_path, "
            "commit_sha=excluded.commit_sha, updated_at=now()",
            (p.name[:4], title(s), status(s), s, str(p), sha))
    for p in architecture:
        s = p.read_text()
        conn.execute(
            "insert into architecture_docs (path, title, status, body, commit_sha, updated_at) "
            "values (%s,%s,%s,%s,%s,now()) on conflict (path) do update set title=excluded.title, "
            "status=excluded.status, body=excluded.body, commit_sha=excluded.commit_sha, updated_at=now()",
            (str(p), title(s), status(s), s, sha))
print(f"synced {len(decisions)} decisions and {len(architecture)} architecture docs at {sha[:7]}")
