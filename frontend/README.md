# Product Intelligence frontend

Authenticated PM workspace using the BMW design tokens from [`design.md`](../design.md).
All business data is requested through the backend's `/api`. There are no generated portfolios,
source excerpts, scores, trends or browser-only research results.

## Run locally

Use Node 24 LTS and start both services from the repository root:

```bash
make dev
```

The frontend runs on `http://localhost:5173`; Vite proxies `/api` to the backend on port 8000.
`BACKEND_PORT=8001 make dev` changes both the backend port and proxy destination. For a separately
started frontend, set `VITE_API_PROXY` to the backend origin if it uses another port.

Sign in with an account created by an administrator using `python -m app.auth.manage`. Passwords
are entered at its hidden prompt. There is no browser sign-up. The session token is kept in
`sessionStorage`, sent as a Bearer header and removed when the session expires or the user signs out.

## What works

- Overview reads scoped feedback/study counts, recorded sales and forecasts, catalog equipment,
  accepted agent contributions and the database audit trail.
- Vehicle-line and market selectors use active database ontology labels. The initial scope includes
  all lines and markets; no vehicle programme is selected implicitly.
- Requirements lists stored backlog rows with their latest persisted score and finding citations.
  Missing scores, confidence, metrics and source links remain missing. Filters and CSV exports use
  only returned rows. Status reviews require a reason and persist through an authenticated API with
  an audit event and a stale-edit check.
- Research uses the backend planner, Critic-gated agents and existing web-search integrations. The
  selected scope is included in new requests. Plan edits, start, acceptance, summary edits, retries
  and gap-or-abort rejection use backend endpoints. Running work is polled.
- Evidence shows loaded sources, source URLs, exact coverage and cited search results. Coverage
  uses the newest non-forecast sales year in the database rather than a fixed year.
- Reports use the same database snapshot as the workspace, with stored citations, accepted research,
  decision history, CSV/research exports and browser print/save as PDF.

The runner retains accepted drafts and scores as step JSON; it does not automatically publish them
into the backlog tables. Accepted contributions remain visible in Overview and Reports, while the
Requirements view accurately shows the existing backlog. Target editing, synthetic trend charts,
local document registration and local scoring weights were removed with the fixture workspace.
Scheduling, durable recovery and a PM ingestion API remain future work. Old local demo storage is
ignored and is never imported as real evidence.

## Verification

```bash
npm run build
npm run lint
npx playwright install chromium
npm test
```

Browser tests mock the API and verify desktop/mobile data reads, empty/error states, authentication,
review persistence, missing versus zero scores, cited exports, live runner actions and automated axe
WCAG checks. Test fixtures are kept under `tests/` and are never shipped as product data.

## Structure

- `src/App.tsx`: authenticated navigation, database scope and snapshot loading.
- `src/data.ts`: formatting and CSV/download utilities; no data fixtures or scoring defaults.
- `src/context.tsx`: the current API snapshot and workspace actions.
- `src/components/`: Overview, Requirements, Research, Evidence and Reports with review dialogs.
- `src/features/`: authentication, agent review flow and evidence retrieval.
- `src/lib/api.ts`, `src/types/api.ts`: API client and mirrored backend response shapes.
- `src/styles.css`: BMW tokens, responsive layouts, print and reduced-motion styles.

## Deployment

Build with `npm run build`, publish `dist`, and serve `/api` on the same origin through a backend or
reverse proxy. Static hosting alone supplies no database access. Hash navigation needs no page
rewrites. Business data always requires the API in development and production; no live-mode flag
or offline fixture fallback exists. Keep database and AI credentials exclusively on the backend.
`vercel.json` retains the Vite build and security headers; add an API proxy when hosting there.

The data and persistence boundary is recorded in [decision 0023](../docs/decisions/0023-database-backed-workspace.md).
