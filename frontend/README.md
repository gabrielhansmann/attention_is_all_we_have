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
- **Evidence**: search customer feedback and catalog text with filters; every hit shows its citation. Exact counts by group.
- **Sources**: coverage per vehicle line and market with gaps marked, and the loaded source files.

## Structure

- `src/App.tsx`: sign-in gate, top bar, hash navigation.
- `src/features/{auth,research,evidence,library}/`: the views.
- `src/lib/api.ts`, `src/types/api.ts`: the API client and its types (mirrors `backend/app/api/schemas.py`).
- `src/components/ui/`, `src/index.css`: shadcn components and the BMW tokens.

## Deploying

Serve the `dist` build from an origin that also serves `/api` (see `vercel.json` for the Vercel settings). Keep
database and AI keys on the backend; never expose them through `VITE_*`.
