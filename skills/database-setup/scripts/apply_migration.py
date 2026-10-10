"""Apply a SQL migration file to the project database from any shell (no MCP needed).

Usage (repo root):
  python skills/database-setup/scripts/apply_migration.py supabase/migrations/<file>.sql [--name NAME] [--dry-run]

- Runs the whole file in ONE transaction with no statement timeout, so long migrations finish
  instead of timing out on the client.
- Records it in supabase_migrations.schema_migrations like the Supabase tools do, so the
  history stays complete. A migration whose name is already recorded is skipped.
- --dry-run runs everything (including the history insert) and then rolls back.
Reads SUPABASE_DB_URL from .env. Never prints secrets.
"""
import argparse
import datetime
import os
import re
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv(".env")

ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--name", help="migration name; default: file name without the leading date and extension")
ap.add_argument("--dry-run", action="store_true")
args = ap.parse_args()

path = Path(args.file)
sql = path.read_text()
name = args.name or re.sub(r"^\d+_", "", path.stem)
if not os.environ.get("SUPABASE_DB_URL"):
    sys.exit("SUPABASE_DB_URL is not set in .env (see skills/database-setup/SKILL.md)")

conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=10)  # autocommit off: one transaction
conn.execute("set statement_timeout = 0")
if conn.execute("select 1 from supabase_migrations.schema_migrations where name = %s", (name,)).fetchone():
    print(f"skip: a migration named '{name}' is already recorded")
    sys.exit(0)

version = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S")
try:
    conn.execute(sql)
    conn.execute(
        "insert into supabase_migrations.schema_migrations (version, name, statements) values (%s, %s, %s)",
        (version, name, [sql]))
except Exception as e:
    conn.rollback()
    sys.exit(f"FAILED, rolled back, nothing applied: {str(e).strip().splitlines()[0]}")

if args.dry_run:
    conn.rollback()
    print(f"dry run ok: '{name}' ran cleanly and was rolled back")
else:
    conn.commit()
    print(f"applied '{name}' as version {version}")
