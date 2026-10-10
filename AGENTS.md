# Agent rules

Project: BMW hackathon requirement-evidence engine. Architecture docs live in `docs/`
(start at `docs/README.md`); those `.md` files are the source of truth.

## Repository layout

- `backend/` FastAPI app and Python package `app` (`api/`, `knowledge/`, `agents/`, `ingest/`,
  `orchestration/`), tests in `backend/tests/`. Run with `make backend`, test with `make test`.
- `frontend/` Vite + React + TypeScript + Tailwind + shadcn/ui. Run with `make frontend`, build with `make build`.
- `supabase/migrations/` SQL migrations, `docs/` architecture and decisions, `skills/` agent skills,
  `data/` provided BMW files (gitignored). One `.env` at the repo root. See `docs/architecture/12-repo-structure.md`.
- The frontend talks to the backend only through `/api`; it never touches the database directly.
- Put new Python code under `backend/app/`, import it as `app.<package>`, and run scripts as
  `python -m app.<package>.<module>`.

## UI design

- Before generating or changing UI, read `design.md`, `docs/ui-design-guidelines.md` and `docs/frontend-style-guide.md`.
  Find and add components with the shadcn MCP (or `npx shadcn@latest`), use the `frontend-design` skill, and review the
  result in screenshots with Playwright at desktop and mobile sizes before delivering.
- Use the BMW tokens and component rules in `design.md` for all UI.
- Apply the anti-slop workflow in `docs/ui-design-guidelines.md`. BMW's explicit brand rules
  take precedence over generic aesthetic defaults, including white surfaces and the Inter fallback.
  Shape and elevation follow decision 0021 (rounded components, soft shadows), not the rectangular default.

## Database

- Postgres on Supabase (pgvector). To connect, set up a machine or teammate, check the state, apply
  migrations, load data or fix a connection error, read `skills/database-setup/SKILL.md` first.
- Check the connection with `python skills/database-setup/scripts/check_db.py --openai`.
- Never print, log, commit or paste secrets (`SUPABASE_DB_URL`, `OPENAI_API_KEY`, passwords, keys).
- **Every API route needs a signed-in user by default.** New routers go into the `protected` router in
  `backend/app/api/__init__.py`. Only `/api/health` and `/api/auth/login` are public; a test checks every route, so do
  not add to the public list without a decision record. Never print or commit tokens or passwords; users are created
  by a human with `python -m app.auth.manage`.
- Agents read evidence through `backend/app/knowledge/tools.py`, not hand-written SQL.

## Pushing

1. **Only push when the user asks.** Never push on your own initiative.
2. **Always squash before pushing.** Collapse all local work since the branch diverged from
   `main` into a single commit (`git reset --soft $(git merge-base HEAD origin/main)` then
   commit, or `git merge-base` + `git rebase -i` equivalent without interactive flags). One push
   = one commit.
3. **Commit message:** imperative subject line, then a short body listing what changed and why.
   Mention any `docs/decisions/` entry added or changed.
4. **Never push to `main` directly** unless the user explicitly says so; work on a branch and
   open a PR. Never force-push `main`. Force-pushing your own feature branch after a squash is
   fine (`--force-with-lease`).
5. **Never commit** `data/` (BMW-provided files), `.env`, or any secret. Check `git status`
   before committing; if any of those show up as staged, stop and fix `.gitignore`.

## Docs and design decisions

- When a design decision changes, edit the relevant `docs/architecture/*.md` in place, bump its
  `Last updated` date, and add a dated entry in `docs/decisions/` (see `docs/decisions/README.md`).
  Do this in the same commit as the code change that motivated it.

## Syncing to Supabase after a push

After a successful push, sync the project record to Supabase. Any agent can do this from a shell:

1. Run `python skills/database-setup/scripts/sync_docs.py` from a checkout of the pushed commit. It
   upserts `docs/decisions/*.md` into `design_decisions` and `docs/architecture/*.md` into
   `architecture_docs` with the commit sha. (Supabase MCP tools may be used instead if available.)
2. Schema changes go through `python skills/database-setup/scripts/apply_migration.py <file>`
   (try `--dry-run` first), never ad-hoc DDL, and the migration file is committed in the same
   squashed commit.
3. Check the current state with `python skills/database-setup/scripts/check_db.py` before changing
   schema, and review the Supabase advisors after DDL.
4. Report what was synced in the final message. If a sync step fails or is skipped, say so
   explicitly. Do not claim the sync is done.

The git repo is the source of truth; Supabase is a mirror. Never edit docs only in Supabase.
