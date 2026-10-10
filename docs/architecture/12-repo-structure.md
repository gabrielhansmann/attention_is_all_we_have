# Repository structure: frontend and backend

> Status: `building` · Last updated: 2026-10-11 (Git-backed full-stack deployment; see [decision 0027](../decisions/0027-git-backed-full-stack-vercel-deployment.md))

```mermaid
flowchart LR
    UI["frontend<br/>React + shadcn/ui"] -->|"/api (JSON)"| API["backend<br/>FastAPI"]
    API --> K["knowledge layer<br/>retrieval tools"]
    API --> O["orchestration<br/>step state machine"]
    O --> AG["agents"]
    AG --> K
    K --> DB[("Supabase Postgres<br/>+ pgvector")]
    ING["ingest<br/>loaders, parsers"] --> DB
    AG -->|findings| DB
    K -.->|embeddings, answers| OAI["OpenAI API"]
```

The browser never talks to the database or to OpenAI. The only door is the backend's `/api`.

## Layout

```
backend/
  pyproject.toml          dependencies, pytest config; `pip install -e "backend[dev]"`
  app/
    main.py               FastAPI app (CORS, routers)
    config.py             repo-root .env and data/ paths, settings; no secrets in logs
    auth/                 password hashing, users and sessions, the admin script (`python -m app.auth.manage`)
    api/                  HTTP layer: health, evidence search / counts / cite / filters, response schemas
    knowledge/            retrieval tools every agent uses; each hit carries a citation
    agents/               LLM-backed agents (Market & Trend today)
    orchestration/        agent catalog, orchestrator (decides the next agent), the LangGraph loop, step runner, chat persistence
    ingest/               loaders and parsers for PDFs and Excel files, provided or uploaded
    deploy/               repository-root Vercel build, produces public/ from frontend/dist
  tests/                  pytest; no database or OpenAI key needed
frontend/                 Gabriel's PM workspace (npm, Vite + React + TypeScript), see frontend/README.md
  src/App.tsx                shell: sign-in gate, top bar, hash navigation between the three views
  src/features/research/     live research: conversations and the orchestrator's decisions, agent results and final result, read-only (calls /api)
  src/features/library/      live sources view in tabs: source graph, files and upload, websites, coverage matrix (calls /api)
  src/features/evidence/     live evidence search with exact counts (calls /api)
  src/components/ui/         shadcn/ui components used by the live views, restyled with BMW tokens
  src/lib/api.ts             the only place the frontend talks to the backend; src/types/api.ts mirrors the schemas
supabase/migrations/      schema, applied in filename order
docs/                     architecture, decisions, requirements
skills/                   agent skills (database setup, scripts)
data/                     provided BMW files, gitignored
Makefile  .env.example    common tasks and the environment template (one .env at the repo root)
pyproject.toml           Vercel deployment adapter and local backend package source
requirements.txt         installs backend/ with its runtime dependencies
vercel.json              root full-stack build and function settings
public/                  generated CDN frontend build, gitignored
```

## Rules

- **Dependencies point inward.** `api` calls `knowledge` and `orchestration`; `agents` call `knowledge`;
  `knowledge` talks to the database. `api` never writes SQL, and nothing imports from `api`.
- **Python imports are `app.<package>`**, scripts run as `python -m app.<package>.<module>`, so paths
  never depend on the working directory.
- **One source for response shapes:** `backend/app/api/schemas.py`, mirrored by `frontend/src/types/api.ts`.
  Change both together.
- **Every API result that states a fact carries a citation** (file, location, verbatim quote).
- **The frontend never touches the database.** Every live view calls `/api`; all SQL is in the backend. There is no
  demo data in the frontend.
- **UI follows `design.md` and decision 0021:** BMW tokens, rounded components, soft shadows and
  the approved Inter substitute font, no dark theme. Components keep labels above fields and show loading, empty and
  error states.
- **Tests:** `make test` for the backend (the API tests replace the knowledge tools with fakes). The
  frontend is checked by `make build` (type-check and bundle), `make lint`, and `npm test`
  from `frontend/` (desktop/mobile Playwright workflows and automated accessibility checks).

## API today

| Endpoint | Returns |
|---|---|
| `POST /api/auth/login` | public: email and password in, a session token out; every failure reads the same, five wrong passwords lock the account for 15 minutes |
| `GET /api/auth/me`, `POST /api/auth/logout` | who am I; revoke this session |
| `GET /api/health` | database and OpenAI-key status (never connection details) |
| `GET /api/evidence/search?q=&source=feedback\|docs&line=&market=&domain=&polarity=&powertrain=&k=` | cited hits, hybrid vector and keyword search |
| `GET /api/evidence/stats?group_by=&line=&market=...` | exact counts and their total |
| `GET /api/evidence/filters` | the values the UI offers as filters |
| `GET /api/evidence/{kind}/{id}` | the citation for one stored row |
| `GET /api/sources` | every loaded source file with what was extracted from it (comments, passages, options, study cells, sales rows) |
| `POST /api/sources?filename=&line=&replace=` | upload one PDF or Excel file as the raw request body; it is stored by the loaders in `app/ingest` and the answer reports what was stored and skipped ([decision 0023](../decisions/0023-file-upload-reuses-the-loaders.md)) |
| `POST /api/sources/web` | fetch one public web page (`url`, optional `line`, `market`, `trust_tier`, `replace`) and store its text as cited passages ([decision 0024](../decisions/0024-websites-as-sources-and-tabbed-sources-view.md)) |
| `DELETE /api/sources/{id}` | remove a stored website and its passages; files are refused |
| `GET /api/sources/graph` | rows each source holds per vehicle line and market, for the graph view |
| `GET /api/sources/web-research` | websites the web agents read during runs, from the stored step outputs |
| `GET /api/evidence/coverage` | comments, study cells and 2025 sales per vehicle line and market, so gaps are visible |
| `GET /api/agents` | the agent catalog in pipeline order and which agents exist yet |
| `GET, POST /api/conversations` | list, or create (optionally with a first request) |
| `GET, PATCH /api/conversations/{id}` | the thread (messages and runs with steps), or rename / archive |
| `POST /api/conversations/{id}/messages` | a PM request: stored at once; the orchestrator then calls agents on its own in the background (409 while the previous request is still running) |

Everything except `/api/health` and `/api/auth/login` needs `Authorization: Bearer <token>`; without it the answer is a
uniform 401 and no database connection is opened. Bad parameters give 422, unknown rows 404, and an unreachable database 503 with no internals in the
message. Interactive docs are served at `/docs`.

## Not built yet

- A separate worker or queue for runs (they execute in the API process; a restart resumes them, decision 0019).
- Successor target editing and scheduled reports. Requirement, tracking and dossier views are implemented.
- A Docker setup and CI.

## Frontend delivery

The UI includes live research, models, requirements, tracking, dossiers, evidence and sources documented in
[the frontend guide](../../frontend/README.md). It holds no fixtures and needs `/api` on its origin; Vite proxies it
in development. Dependencies use the npm lockfile; the Makefile installs with `npm ci`.

## Model overviews (decision 0025)

`backend/app/comparisons/` contains local catalog parsing, public-source discovery/scraping,
quote validation and the context-loaded chat adapter. `backend/app/knowledge/models.py` owns
model evidence access and deterministic cohort median/mean calculations. `backend/app/api/models.py`
exposes the authenticated `/api/models` endpoints. `frontend/src/features/models/` renders the
compact model/variant/market comparison workspace, diagrams, source validation controls and
the existing chat. `20261016_model_comparisons.sql` adds the persistence and chat bindings.
All comparisons are calculated by the server against Supabase; no database keys or business
fixtures are shipped to the frontend.

## Vercel deployment (decision 0027)

Deploy from the repository root. The root pyproject.toml points Vercel to the existing FastAPI
deployment adapter and installs the locally sourced backend package (requirements.txt supports pip).
`app.deploy.build` runs the
frontend lockfile install and production build, then prepares public/ for CDN delivery.
The adapter registers the generated frontend with FastAPI for explicit CDN promotion. Protected
API routes take priority. Hash navigation requires no SPA fallback, preserving missing-file and
disabled-documentation errors. A frontend-only dependency returns 404 when CDN promotion omits
the static directory from the function bundle; API routes retain their normal handlers.
The API shares that origin and uses
encrypted server-only Supabase/OpenAI configuration.
The root ignore/configuration files omit credentials, BMW files and development artifacts.
Deployment runs no migrations or user-management commands. The local `make dev` workflow remains.
