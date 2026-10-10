# 0017 — Minimal, live-only frontend: the demo workspace and its fixtures are removed

> Date: 2026-10-14 · Status: accepted · Supersedes [0011](0011-local-demo-frontend-and-vercel.md) and the demo half of [0013](0013-frontend-uses-only-the-backend-api.md)

## Context

The frontend was a five-view PM workspace over hardcoded fixtures (requirements, targets, trends, reports) kept in
browser storage, with the real backend views hidden behind a "live" switch. Most of the demo has no backend counterpart,
so it showed numbers that were not evidence, and it carried a large amount of custom CSS next to the shadcn components.

## Decision

1. **No hardcoded data.** `data.ts`, the browser-stored workspace, and the Overview, Requirements, Reports, demo Research
   and demo Evidence views are deleted. Every value on screen comes from `/api`. Vehicle line and market appear as the
   codes the API returns; filter labels come from `/api/evidence/filters`.
2. **Three views, one shell.** Research (planner), Evidence (search and counts) and Sources (coverage and files), in a
   plain top bar with hash navigation. Sign-in is a full page; without a token nothing else renders.
3. **One styling system.** Tailwind with the BMW tokens in `index.css` and the shadcn components. The custom
   `styles.css`, Radix dialog, Phosphor icons and react-router are removed.
4. **Deployment.** There is no offline demo mode any more, so a deployed frontend needs `/api` served on its origin.
   `VITE_LIVE_EVIDENCE` is no longer read.

## Consequences

Views for requirements, targets and reports return when the backend has the data behind them, built then on the same
shell. The static Vercel demo of the fixtures no longer exists.
