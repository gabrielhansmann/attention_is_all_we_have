# Product Intelligence frontend

A minimal React UI over the backend API. It holds no demo data: everything on screen comes from `/api`.
Design rules are in [`design.md`](../design.md) and [`docs/ui-design-guidelines.md`](../docs/ui-design-guidelines.md);
the decision is [0017](../docs/decisions/0017-minimal-live-only-frontend.md).

## Run locally

Node 24 LTS (or another version supported by Vite 7). From the repo root, `make dev` runs backend and frontend; or:

```bash
cd frontend
npm ci
npm run dev      # /api is proxied to http://localhost:8000, or VITE_API_PROXY
npm run build    # type-check and production build
npm test         # Playwright, desktop and mobile, with axe checks; every API call is mocked
```

## Views

- **Sign in**: shown whenever there is no valid session. There is no sign-up; an administrator creates users with
  `python -m app.auth.manage`. The token is kept in `sessionStorage`, sent as a Bearer header and dropped on any 401.
- **Research**: send a request and watch the orchestrator work. It chooses agents itself, reads each result and
  decides whether to call another ([decision 0018](../docs/decisions/0018-orchestrator-decides-in-an-agentic-loop.md)).
  The thread shows each decision with its reason, each agent's cited result and the final result. Nothing to approve.
  It refreshes while a run is in progress; one request runs at a time.
- **Requirements**: requirements from finished runs, each with target, acceptance criteria and sources. Approve, challenge
  or reject (a reason is asked for). The Priorities tab re-ranks with weight sliders (a what-if, not saved) and shows
  customer need against business signal ([decision 0022](../docs/decisions/0022-requirement-register-and-process-views.md)).
- **Tracking**: approved requirements under watch. "Check for new evidence" flags new, contradicting or old evidence.
- **Dossiers**: the written record of each run, with citations that open the source.
- **Evidence**: search customer feedback and catalog text with filters; every hit shows its citation. Exact counts by group.
- **Sources**: a graph of what each source covers, the loaded files with upload, websites (added by address or read by agents), and coverage per vehicle line and market with gaps marked.
  A PDF or Excel file can be added here; the backend stores it and reports what it read.

## Structure

- `src/App.tsx`: sign-in gate, top bar, hash navigation.
- `src/features/{auth,research,evidence,library}/`: the views.
- `src/lib/api.ts`, `src/types/api.ts`: the API client and its types (mirrors `backend/app/api/schemas.py`).
- `src/components/ui/`, `src/index.css`: shadcn components and the BMW tokens.

## Deploying

Deploy Vercel from the repository root using the root `vercel.json` and `pyproject.toml`.
`PYTHONPATH=backend python -m app.deploy.build` installs the frontend lockfile, builds it and
copies `dist` to root `public/` for the CDN. The same deployment serves the existing protected
FastAPI `/api` routes. Runtime dependencies come from the backend package. Keep database and AI
keys encrypted on the backend; never expose them through `VITE_*`.
The frontend-only `frontend/vercel.json` does not package the API.
See [decision 0027](../docs/decisions/0027-git-backed-full-stack-vercel-deployment.md).


## Model comparisons

Open `#models` for the Supabase-derived model inventory, registered variants and Germany/Europe
default market. The protected `/api/models` backend owns the cohort, source extraction, median
and mean. Up to six measured charts distinguish the reference model (BMW blue), each rival
(gray), competitor median (dark) and competitor mean (dashed). Reported ranges retain both
endpoints. Feature claims use an evidence matrix; absent evidence is not an absent feature.

Every rival card has **Crawl rival sources** and **Reevaluate rival** actions, including a
first crawl before any finding exists. Every finding exposes its quote, source, crawl/evaluation
time and validation controls. Refreshes preserve prior citations. Add a competitor by name, or
supply an exact variant and an optional official technical page/PDF when discovery needs help.
The model chat reuses the existing research component and receives the server's current model,
variant, market, selected competitors and cited evidence on each request.

See [benchmarking architecture](../docs/architecture/10-competitor-benchmarking.md) and
[decision 0025](../docs/decisions/0025-server-owned-model-comparisons.md). Inaccessible sources and
incompatible measurements remain explicit gaps; the application does not fabricate benchmarks.
