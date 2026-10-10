# Repository structure: frontend and backend

> Status: `building` · Last updated: 2026-10-11 (see [decision 0010](../decisions/0010-frontend-backend-repo-structure.md))

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
    api/                  HTTP layer: health, evidence search / counts / cite / filters, response schemas
    knowledge/            retrieval tools every agent uses; each hit carries a citation
    agents/               LLM-backed agents (Market & Trend today)
    orchestration/        step state machine (planned, running, awaiting_review, accepted, rejected)
    ingest/               loaders and parsers for the provided PDFs and Excel files
  tests/                  pytest; no database or OpenAI key needed
frontend/
  src/
    components/ui/        shadcn/ui components (generated, restyled with BMW tokens)
    components/layout/    app shell, backend health badge
    components/evidence/  citation block, hit card, filter select
    features/evidence/    evidence explorer (live, uses the API)
    features/chat/        chat workspace shell (orchestrator not connected yet)
    lib/api.ts            typed API client
    types/api.ts          mirrors backend/app/api/schemas.py
supabase/migrations/      schema, applied in filename order
docs/                     architecture, decisions, requirements
skills/                   agent skills (database setup, scripts)
data/                     provided BMW files, gitignored
Makefile  .env.example    common tasks and the environment template (one .env at the repo root)
```

## Rules

- **Dependencies point inward.** `api` calls `knowledge` and `orchestration`; `agents` call `knowledge`;
  `knowledge` talks to the database. `api` never writes SQL, and nothing imports from `api`.
- **Python imports are `app.<package>`**, scripts run as `python -m app.<package>.<module>`, so paths
  never depend on the working directory.
- **One source for response shapes:** `backend/app/api/schemas.py`, mirrored by `frontend/src/types/api.ts`.
  Change both together.
- **Every API result that states a fact carries a citation** (file, location, verbatim quote).
- **UI follows `design.md`:** BMW tokens, rectangular components, no shadows, Inter 300/700 as the
  approved substitute font, no dark theme. Components keep labels above fields and show loading, empty and
  error states.
- **Tests:** `make test` for the backend (the API tests replace the knowledge tools with fakes). The
  frontend is checked by `make build` (type-check and bundle) and `make lint`; it has no test runner yet.

## API today

| Endpoint | Returns |
|---|---|
| `GET /api/health` | database and OpenAI-key status (never connection details) |
| `GET /api/evidence/search?q=&source=feedback\|docs&line=&market=&domain=&polarity=&powertrain=&k=` | cited hits, hybrid vector and keyword search |
| `GET /api/evidence/stats?group_by=&line=&market=...` | exact counts and their total |
| `GET /api/evidence/filters` | the values the UI offers as filters |
| `GET /api/evidence/{kind}/{id}` | the citation for one stored row |

Bad parameters give 422, unknown rows 404, and an unreachable database 503 with no internals in the
message. Interactive docs are served at `/docs`.

## Not built yet

- Chat endpoints and the orchestrator that plans and runs agents (needs the `conversation` and
  `message` tables and the new step states from decision 0005).
- Authentication: the API is open, which is fine for a local demo and must change before it is exposed.
- A Docker setup and CI.
