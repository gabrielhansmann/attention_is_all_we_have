# Tech stack

> Status: `building` · Last updated: 2026-10-10 (database workspace; [decision 0023](../decisions/0023-database-backed-workspace.md))

| Layer | Implemented choice | Boundary |
|---|---|---|
| Orchestration | Python planner and state machine; FastAPI background tasks with separate connections | Sequential PM gates, Critic retries and step JSON persistence. LangGraph/checkpointed durable execution remains planned; a server interruption can leave a running step stuck. |
| Models | OpenAI API for planning, extraction, clustering and drafting | Sales/Portfolio findings, scoring, Documentation, Delta/Tracking and Critic checks are deterministic. See the model-use table in [01-agents.md](01-agents.md#implementation-status). |
| Web research | OpenAI Responses API built-in `web_search` | URLs come from citation annotations. Stored snippets are cited summaries, not full-page verbatim snapshots. No separate scraper or search API is implemented. |
| PDF parsing | Poppler `pdftotext -layout` plus pdfplumber | Text passages and positional equipment/variant extraction are implemented. Packages and technical-value pages remain searchable text rather than complete relational specifications. |
| Excel | openpyxl and psycopg loaders | Feedback, line/market/year sales and customer-study cross-tabs with row or cell locators. No measured option take-rate or study respondent counts are supplied. |
| Storage | Supabase Postgres and pgvector | Evidence, chat, steps, users, sessions and append-only audit events. Runs store outputs on steps; accepted results are not yet written into backlog tables. RLS is enabled; backend access only. |
| Embeddings | OpenAI `text-embedding-3-small`, 1536 dimensions | Feedback comments, PDF chunks and the finding schema support vectors. Options and sales remain exact structured data. A different embedding model needs a migration and re-embedding. |
| API | FastAPI and uvicorn | Evidence/library, planning, execution and review endpoints. All except health and login require a Bearer session. `APP_ENV=production` hides OpenAPI and interactive docs. |
| Authentication | scrypt passwords and server-side hashed sessions | Admin CLI creates invited users; logout, password changes and deactivation revoke sessions. Concurrent sign-in attempts lock the account row to preserve failed-attempt counts. |
| Frontend | React, TypeScript, Vite, Tailwind and shadcn-style primitives | BMW tokens and self-hosted Inter. Local live research now runs and reviews backend steps; live evidence shows citations and coverage. |
| Frontend persistence | Authenticated backend API for every business view | Database ontology, raw evidence, backlog rows/latest scores, accepted step JSON and audit events. Requirement status reviews persist atomically; no browser business-data store or fixture fallback. |
| Deployment | Vite frontend with backend `/api`; Supabase database | Development uses the Vite proxy. Production must serve `/api` on the same origin through a hosted backend/proxy; static files alone cannot supply the workspace. |

The frontend calls only `/api`, never Supabase or OpenAI directly. Provider and database credentials stay
on the backend. See [the frontend guide](../../frontend/README.md) for setup, data boundaries and tests.

Recurring refresh, weekly reports, broader input ingestion, backlog persistence and durable recovery remain
planned. No production worker model or measured recommendation accuracy is claimed.
