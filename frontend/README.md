# Product Intelligence frontend

A working, responsive PM workspace based on [`docs/idea.md`](../docs/idea.md),
[`design.md`](../design.md), and the architecture docs. Uses the documented BMW blue,
white, and navy palette, rectangular controls, Inter, and Phosphor icons.

Live demo: [bmw-product-intelligence.vercel.app](https://bmw-product-intelligence.vercel.app).

## Run locally

Use Node 24 LTS (or another version supported by Vite 7).

```bash
cd frontend
npm ci
npm run dev
```

Open the local URL printed by Vite. Production build:

```bash
npm run build
npm run preview
```

## What works

- Overview with vehicle-line/market selection, baseline comparisons, editable successor
  targets and priorities, illustrative trend charts, and decision history.
- Requirement portfolio with search, filters, explainable weighted scores, editing,
  reason-required approval/challenge/rejection, and filtered CSV exports with citations.
- Guided research with sequential Accept/Edit/Retry/Reject gates. Rejections require a
  continue-with-gap or abort decision. Drafts appear only after the final review.
- Evidence library with source locators, linked requirements, coverage gaps, and local
  document registration. Text/CSV/JSON files include a preview; binary files are not parsed.
- Programme report with targets, requirements, citations, history, CSV export, and
  browser print/save as PDF.
- Browser persistence, JSON workspace export, and an explicit reset confirmation.

All seed values, excerpts, grades, and trends are **illustrative demo fixtures**, not verified
BMW specifications or findings. Research does not call an AI provider, query Supabase, or
search the web. Retry records steering against the same fixtures. Plans use three fixed
steps, rather than the proposed live orchestrator. No automated report scheduling runs.

In local development, **Evidence library → Browse backend evidence** opens the retained live
Evidence browser. Run `make backend` at the repo root to serve its `/api` requests; Vite
proxies them to port 8000, or `VITE_API_PROXY` when set. This mode has separate search filters
and does not import live hits into the local portfolio. It is disabled in the static Vercel
demo; another deployment can enable it with `VITE_LIVE_EVIDENCE=true` once `/api` is served.

Edits and previews are stored in this browser's local storage. There is no account system,
server persistence, shared workspace, immutable audit log, or restore-from-JSON UI yet.
Export a backup to retain work outside this browser. See
[decision 0011](../docs/decisions/0011-local-demo-frontend-and-vercel.md) for the boundary
between the delivered frontend and the planned backend.

## Verification

```bash
npx playwright install chromium
npm test
```

Playwright exercises desktop and mobile workflows, persistence, exports, review gates,
keyboard dialog focus, PDF generation, overflow, and automated axe WCAG checks on all five
views. Tests require a browser environment that permits Chromium to launch.

## Structure

- `src/App.tsx`: navigation, scope, dialogs, and persisted workspace state.
- `src/data.ts`: typed demo fixtures, scoring, citations, CSV, and export utilities.
- `src/context.tsx`: shared workspace actions.
- `src/components/`: the five views, forms, and Radix-based dialog/button primitives.
- `src/styles.css`: brand tokens, responsive layouts, print, and reduced-motion styles.
- `src/features/evidence/`, `src/lib/api.ts`: retained backend Evidence browser and API client.
- `src/index.css`, `src/shadcn-variants.css`: retained Tailwind/Base UI styling.

## Vercel

Deploy **this directory** as a Vite project, with `npm run build` and output directory
`dist`. `vercel.json` contains these settings. Hash navigation allows all workspace views
to load and refresh from the static entry point. The Latin Inter font is hosted with the
app; the frontend needs no environment variables or backend credentials.

```bash
cd frontend
vercel --prod
```

`.vercelignore` excludes dependencies, test artifacts, and environment files from uploads.
Keep service-role/database/AI keys on a future backend; do not expose them through `VITE_*`.
Deployments currently use the CLI; Git-triggered deployments are not configured.
