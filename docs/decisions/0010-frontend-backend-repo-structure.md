# 0010 — Split the repository into a FastAPI backend and a React frontend

> Date: 2026-10-11 · Status: accepted · Supersedes the flat layout (`agents/`, `ingest/`, `knowledge/`, `tests/`) used by decisions 0006 and 0008

## Context

The code grew as flat top-level folders with paths hard-coded to the repo root as the working directory.
The tech-stack doc already named FastAPI and React + shadcn/ui and the product needs a chat UI, but there was
no API and no frontend, and Python scripts could not be imported as a package.

## Decision

1. **`backend/`** is one Python package `app` (FastAPI): `api`, `knowledge`, `agents`, `orchestration`,
   `ingest`. Existing modules moved with `git mv`, imports became `app.<package>`, scripts run as
   `python -m app.<package>.<module>`, and a shared `config` module finds the repo-root `.env` and `data/`
   from any directory.
2. **`frontend/`** is Vite + React + TypeScript + Tailwind v4 + shadcn/ui, themed with the BMW tokens from
   `design.md`. It reaches the backend only through `/api` (dev proxy, so one origin and no CORS in dev).
3. **Shared root:** one `.env`, `supabase/migrations/`, `docs/`, `skills/`, `data/`, a `Makefile` and a
   `.env.example`.
4. **Vite over Next.js:** the backend is Python and owns all server logic, so the frontend is a static
   single-page app. No second server runtime is needed and any static host can serve it.
5. **The browser never holds a database credential or an OpenAI key.** All evidence reads go through the
   API, which returns citations with every fact.
6. **First vertical slice:** the Evidence screen (live search, filters, exact counts, citations) proves the
   whole path from browser to database. The Chat screen is the real empty state until the orchestrator exists.

## Consequences

- Open branches that edit `agents/`, `ingest/`, `knowledge/` or `tests/` need to rebase onto the new paths
  (`git mv` keeps history, so renames are detected).
- `pip install -r ingest/requirements.txt` is replaced by `pip install -e "backend[dev]"`.
  This also fixes a missing dependency: `openpyxl` was imported but never listed.
- The API has no authentication and a single shared database connection. Both are acceptable for a local
  demo and must change before any deployment.
- Not decided here: Docker, CI, and a frontend test runner.

See [`../architecture/12-repo-structure.md`](../architecture/12-repo-structure.md).
