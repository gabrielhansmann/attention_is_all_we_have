---
name: database-setup
description: Connect to and set up the project's Supabase Postgres database (pgvector) with an OpenAI API key. Use when a task needs database access, when a connection or OpenAI call fails, when setting up a new machine or teammate, when applying or writing migrations, or when loading the BMW data. Works from any agent shell with Python; no MCP or vendor-specific tool required.
---

# Database setup (Supabase Postgres + pgvector, OpenAI embeddings)

One Supabase project holds everything: raw evidence, embeddings, findings, requirements, audit log.
Everything below runs from a plain shell with Python, so it works the same for OpenAI Codex, ChatGPT
agents, Claude Code, Cursor or a human. Agents that have a Supabase MCP connection may use it, but
nothing here depends on it.

Never print, log, commit or paste a password, connection string or API key. Refer to variable names only.

## 1. Prerequisites

- Python 3.11+ and `make install` (or `python3 -m venv .venv && .venv/bin/pip install -e "backend[dev]"`); installs `fastapi`, `openai`, `psycopg`, `pdfplumber`, `openpyxl`, `python-dotenv`
- `pdftotext` / `pdfinfo` (poppler) only to re-run the PDF loaders
- The BMW files in `data/` (gitignored) only to re-run loaders. The data is already loaded.
- A Supabase login or database role from the project owner (section 6) and an OpenAI API key

## 2. Configure `.env` (repo root, gitignored)

```
OPENAI_API_KEY=sk-...                  # your own key
SUPABASE_DB_URL=postgresql://USER:PASSWORD@HOST:5432/postgres
OPENAI_CHAT_MODEL=gpt-4o-mini          # optional: model used by `app.ingest.ask_pdf` and `app.ingest.seed_ontology`
```

Each variable on its own line (a file without a trailing newline glues the next line on). URL-encode
special characters in the password (`@` is `%40`, `/` is `%2F`).

**OpenAI usage in this project**
- Embeddings: `text-embedding-3-small`, 1536 dimensions, fixed in the database columns. Used by the loaders
  and by every search in `backend/app/knowledge/tools.py`. The key needs embeddings access.
- Chat/answers: `OPENAI_CHAT_MODEL` (default `gpt-4o-mini`). Change it freely; it does not affect stored data.
- Switching the embedding model means re-embedding all rows and altering the vector columns.
- Costs are small: the full dataset (~14k comments, 149 PDF chunks) embeds for a few cents.

**Where the database string comes from:** Supabase dashboard -> **Connect** -> Connection string.

| Option | Host looks like | Use when |
|---|---|---|
| **Direct** | `db.<project-ref>.supabase.co:5432`, user `postgres` | your network has IPv6 |
| **Session pooler** | `aws-0-<region>.pooler.supabase.com:5432`, user `postgres.<project-ref>` | IPv4-only network; also what LangGraph's checkpointer needs |
| Transaction pooler | port `6543` | **do not use**: breaks prepared statements used by psycopg |

Teammates should use their own role (section 6), not the `postgres` admin password.

## 3. Verify

```
python skills/database-setup/scripts/check_db.py --openai   # or: make check-db
```

Checks the variables, connects, and reports pgvector, every expected table with row counts, the search
functions and the vector indexes. `--openai` also makes one tiny embeddings call to prove the key, the
model and the 1536-dimension size. Exit code 0 means ready. Expected row counts today: `feedback_raw`
13,771, `chunk` 149, `option` 198, `option_availability` 1,352, `sales_volume` 36, `study_response` 1,627;
`finding` and the tables after it are empty until agents write to them.

Then try the retrieval tools: `python -m app.knowledge.tools` (from `backend/`, or after `pip install -e backend`).

## 4. Schema and migrations

- Migrations live in `supabase/migrations/`, applied in filename order. The file in the repo must match
  what was applied.
- **Apply a migration with the script** (works from any shell, no client timeout):

```
python skills/database-setup/scripts/apply_migration.py supabase/migrations/<file>.sql --dry-run   # test, rolls back
python skills/database-setup/scripts/apply_migration.py supabase/migrations/<file>.sql             # apply for real
```

  It runs the file in one transaction, records it in `supabase_migrations.schema_migrations` (so the
  history stays complete), skips a name that is already recorded, and rolls back on any error.
  Do not apply schema changes with ad-hoc SQL. Inspect the current state first (`check_db.py`), and
  afterwards check Supabase's security and performance advisors in the dashboard.
- **Heavy migrations:** rewriting all 13.7k `feedback_raw` rows with the HNSW index takes minutes. For a bulk
  update, drop the HNSW index first, update in one pass, rebuild the index after. If another tool's
  call times out, the server may still be running the statement: look for a running `begin;` in
  `pg_stat_activity` and wait before re-submitting.
- Every table has row level security enabled and **no policies**: only the service role, the `postgres`
  admin, or a role with explicit policies can read or write. The browser/anon key sees nothing.
- `audit_event` is append-only (a trigger blocks update, delete, truncate). Never work around it.

## 5. Load the data (only on a fresh database)

Run in this order (after `pip install -e backend`, from any directory); each loader is idempotent (re-running replaces that file's rows):

```
python -m app.ingest.load_pdfs     # catalog PDFs -> source + chunk (embedded with OpenAI)
python -m app.ingest.load_options  # equipment tables -> option + option_availability
python -m app.ingest.load_excel    # feedback, sales, customer studies (feedback is embedded)
python -m app.ingest.seed_ontology # domains, vehicle lines, markets, category labels (uses the chat model)
```

Loaders connect with `autocommit=True` so each transaction block really commits. A plain connection
with a query before the block silently rolls everything back on close.

## 6. Giving a teammate access

Prefer, in this order:

1. **Dashboard access:** Organization settings -> Team -> Invite, role **Developer** (read-only for viewers).
   They sign in with their own account.
2. **A database role for scripts**, so nobody needs the `postgres` password. Template (tested; run as admin
   and replace the password with a generated one):

```sql
create role team_rw login password '<generated>';
grant usage on schema public, extensions to team_rw;
grant select, insert, update, delete on all tables in schema public to team_rw;
grant execute on all functions in schema public to team_rw;
do $$ declare t text; begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('create policy team_rw_all on public.%I for all to team_rw using (true) with check (true)', t);
  end loop; end $$;
```

   RLS is on, so the role needs those policies to see rows. Read-only variant: grant `select` only and
   create the policies `for select`. Their string is
   `postgresql://team_rw.<project-ref>:<password>@<pooler-host>:5432/postgres` (pooler) or
   `postgresql://team_rw:<password>@db.<project-ref>.supabase.co:5432/postgres` (direct). A table created later
   needs the same grants and a policy for the role.
3. Share credentials through a password manager or secure message, never git, chat history or screenshots.
   If a password leaks, reset it (Project Settings -> Database for `postgres`, `alter role ... password` for others).

Never hand out the service-role key. It bypasses all security. Each teammate uses their own `OPENAI_API_KEY`.

## 7. Common errors

| Symptom | Cause and fix |
|---|---|
| `could not translate host name` / `Network is unreachable` | Direct host is IPv6-only. Use the session pooler string |
| `password authentication failed` | Wrong or unencoded password. Reset it and URL-encode special characters |
| `prepared statement ... does not exist` | You are on the transaction pooler (6543). Switch to 5432 |
| `permission denied for table` / queries return 0 rows | Role has no grants or no RLS policy (section 6) |
| `type "vector" does not exist` | Write `extensions.vector(1536)`; the extension lives in the `extensions` schema |
| `openai.AuthenticationError` / 401 | `OPENAI_API_KEY` missing, wrong or revoked. Run `check_db.py --openai` |
| `openai.RateLimitError` / 429 during a loader | Re-run the loader; it replaces the file's rows. Reduce `BATCH` in the loader if it persists |
| `model_not_found` | The key has no access to the model. Set `OPENAI_CHAT_MODEL` to one it can use (embeddings model is fixed) |
| `expected 1536 dimensions` | An embedding model other than `text-embedding-3-small` was used |
| `.env` variable not found by a script | Run from the repo root; each variable on its own line |
| Loader reports success but tables are empty | Connection was not autocommit (section 5) |

## 8. Using this skill from different tools

- `AGENTS.md` (read by Codex and many other agents) points here, so any agent that reads it finds this file.
- If your tool has a skills folder, link or copy `skills/database-setup/` into it (for example
  `.agents/skills/` or `.claude/skills/`; check your tool's docs). Dot-folders are gitignored in this repo,
  so keep the link local.

## 9. After changing the database

Update the matching doc under `docs/` (and add a decision record if a choice changed). After the push,
mirror the docs with `python skills/database-setup/scripts/sync_docs.py` (use `--dry-run` to preview;
run it from a checkout of the pushed commit so it does not overwrite newer mirrored docs). The push rules
are in `AGENTS.md`.
