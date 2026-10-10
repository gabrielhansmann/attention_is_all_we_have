# 0013 — The frontend reaches data only through the backend API; live mode sits beside the demo

> Date: 2026-10-12 · Status: partly superseded by [0023](0023-database-backed-workspace.md) (the backend-only data access rule remains)

## Context

Decision 0011 delivered a standalone demo workspace (fixtures and browser storage) and kept one live Evidence browser.
The backend since gained the chat API and the planner, but nothing in the UI used them, and there was no endpoint that
shows which sources are loaded or where evidence is missing.

## Decision

1. **All data access goes through the backend.** The frontend calls `/api` and never reads the database. Anything the UI
   needs becomes a backend endpoint first. Two read-only endpoints were added: `GET /api/sources` and
   `GET /api/evidence/coverage`.
2. **Live mode sits beside the demo.** Research gets a "Live planner (backend)" switch and the evidence library lists real
   sources and coverage. The fixture views are untouched, so the static Vercel demo keeps working. Live mode is on in local
   development and off in the static build.
3. **No fake controls.** Agents do not run yet, so live research shows the plan and plan editing only, with a note saying so.
   Accept, edit, retry and reject appear when the runner exists.
4. **Gaps are shown as gaps.** The coverage matrix marks a market with no customer feedback (China, in every line), thin
   evidence (under 100 comments) and missing sales or study data.
5. **The dev server listens on localhost only.** It proxies `/api` to an unauthenticated backend, so network exposure
   (`npm run dev:lan`) is an explicit opt-in. `vite preview` is localhost-only too.
6. **Live views mock the API in tests** (Playwright), so no test reaches a real backend or database.

## Consequences

- Two styling systems still coexist (the demo's custom CSS and the shadcn parts). Their tokens collided: `--muted` was a text
  colour in one and a background in the other, which turned every `bg-muted` dark grey (contrast 2.83:1). The shadcn side
  now uses `--ui-muted`. Further collisions are possible; new tokens should be checked against `styles.css`.
- The shadcn destructive badge failed WCAG AA (4.13:1) and now uses a white background with a red border.
- The demo vocabulary is narrower than the backend (no G68, no Rest of world, scope always one line and market). Live views use
  the backend's vocabulary; the demo fixtures are unchanged.
- Remaining: wire Requirements, Overview and Reports once findings and requirements exist, and the runner for live agent steps.

See [`../architecture/12-repo-structure.md`](../architecture/12-repo-structure.md) and decision [0011](0011-local-demo-frontend-and-vercel.md).
