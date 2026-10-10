# 0011 — Local demo PM workspace and static Vercel deployment

Date: 2026-10-10 · Status: superseded by [0023](0023-database-backed-workspace.md)

## Context

The software idea describes a vehicle-specific PM overview, successor targets, evidence,
competitor comparisons, trends, and reports. The repo now has ingestion, a knowledge layer,
and a Market & Trend Agent prototype. Decision 0010 adds a FastAPI evidence API and an initial
Evidence browser; complete live orchestration is still pending. The user requested a working frontend using the documented design and Vercel hosting.

## Decision

Deliver a React/TypeScript Vite workspace in `frontend/`, deployed independently as a static
Vercel application. Use BMW tokens from `design.md`, self-hosted Inter, Phosphor icons, and
Radix dialog/Slot primitives with variant-based buttons following the shadcn component pattern.
Retain the Tailwind/Base UI components and API Evidence browser from decision 0010. Keep its
`@` alias and `/api` dev proxy. The API browser is opt-in from Evidence library in development
or via `VITE_LIVE_EVIDENCE=true` on an origin that serves the API; the static demo keeps it off.
Use an npm lockfile for reproducible installs and update the Makefile accordingly. The unused
shadcn generator is omitted from installed dependencies; the generated components retain their
CSS state variants locally.

Implement five views: Overview, Requirements, Research, Evidence library, and Reports. Local
state supports editable targets and requirement scores, PM decisions with reasons, sequential
review gates, source locators, exports, and a decision history. Scope covers the documented
F70/G60/G70 vehicle codes and EU/US/CN markets with explicitly illustrative fixtures.

Use browser local storage for this demo; all data is clearly labeled illustrative. Research
uses a fixed three-step fixture plan. Accept advances one step, Edit records a revised summary,
Retry records steering without collecting new evidence, and Reject requires an explicit gap
or abort decision. Draft creation waits for the last review. Uploaded files are registered
locally; binary parsing is pending and text previews are unverified.

## Consequences

- The UI can be demonstrated without database access, provider credentials, or runtime API
  dependencies. No real BMW source files, `.env`, or service keys are part of the deployment.
- Vercel hosts only the frontend. This does not deploy or replace the Python agents, ingestion,
  Supabase schema, or the FastAPI backend and proposed LangGraph orchestration.
- Client history is editable browser data, not an immutable server audit trail. There is no
  authentication, shared persistence, automatic web research, or weekly report scheduler.
- A live integration must replace fixtures with scoped, cited API responses, authenticated
  persistence, server audit events, and resumable orchestration before claiming production
  evidence handling. The backend architecture remains the target design.
- Verify the UI with a production build and desktop/mobile browser tests, including review
  gates, persistence, citations, exports, keyboard focus, and automated accessibility checks.
