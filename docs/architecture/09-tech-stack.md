# Tech stack

> Status: `building` · Last updated: 2026-10-11 (live full-stack Vercel deployment, see decision 0027)

Kept boring on purpose — a hackathon is not the place to debug infrastructure.

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph (`StateGraph` in `backend/app/orchestration/loop.py`) with the Postgres checkpointer | The orchestrator model picks the next agent after each result ([decision 0018](../decisions/0018-orchestrator-decides-in-an-agentic-loop.md)); the graph checkpoints its control-flow state per run so a restart resumes it ([decision 0019](../decisions/0019-orchestration-loop-runs-on-langgraph.md)). The checkpointer needs the direct or session-pooler connection string, not the transaction pooler. There are no human gates, so `interrupt()` is unused |
| LLM | Every agent is LLM-backed. Currently the OpenAI API (key in `.env`); the provider is a config choice and Claude remains an option | Extraction, cluster labeling, requirement drafting, scoring rationale, Critic verification, answering over retrieved evidence. Answers may only cite retrieved rows |
| Web research | The LLM's built-in web search tool (OpenAI Responses API `web_search`), for now | No extra search API key or service. Sources are built from the tool's citation annotations, not from model-written text; source-trust tagging is applied at ingest time. A dedicated search API (Tavily/Brave) stays an option, see [decision 0009](../decisions/0009-web-search-through-the-llm.md) |
| PDF parsing | `pdftotext -layout` (poppler) for text; pdfplumber / vision-LLM still planned for the equipment tables | Text extraction works (the catalogs have real text). Reliable ■/□ column mapping needs table-aware extraction or a vision pass — not built yet |
| Excel | openpyxl (+ psycopg for loading) | Loaders in `backend/app/ingest/`; the customer-study cross-tabs need a custom parser |
| Storage | Supabase (managed Postgres) + pgvector 0.8 | One database for both relational entities (`Finding`, `Requirement`, `AuditEvent`, …) and embeddings — keeps traceability joins simple instead of reconciling two stores. Schema is live: see `supabase/migrations/`. RLS is on for every table with no policies yet, so only the backend (service role / direct connection) can read or write; the frontend goes through the API |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, cosine, HNSW) | Key in `.env` as `OPENAI_API_KEY`. Only `finding.text` and `chunk.content` are embedded; option codes and sales numbers stay exact, un-embedded data. Changing the model means re-embedding and altering the column — see [decision 0004](../decisions/0004-supabase-and-openai-embeddings.md) |
| API | FastAPI (`backend/app/api`), uvicorn locally and the Python runtime on Vercel | Backend-owned authentication, live orchestration, evidence, model comparisons and the requirement lifecycle are implemented; see [`12-repo-structure.md`](12-repo-structure.md) |
| Frontend | React + TypeScript + Vite; shadcn with Base UI primitives | Live research, model comparisons, requirements, tracking, dossiers, evidence and sources. BMW tokens, self-hosted Inter and Lucide icons; see [decision 0017](../decisions/0017-minimal-live-only-frontend.md) and [0021](../decisions/0021-rounded-chat-first-frontend.md) |
| Frontend persistence | Supabase through the protected backend API | Browser session storage holds the sign-in token; model evidence, comparison histories, chats and requirements are server-owned. No application fixtures are shipped |
| Deploy | Vercel serves the Vite build and FastAPI on one origin; Supabase hosts Postgres | Root configuration selects the existing backend app. `app.deploy.build` produces the public CDN frontend from its lockfile; runtime dependencies come from backend/pyproject.toml. See [decision 0027](../decisions/0027-git-backed-full-stack-vercel-deployment.md) |

The workspace uses the live backend API for all application data. Vite proxies `/api` to FastAPI
locally; Vercel serves both layers on the same origin. Database and AI credentials remain
server-only. Source uploads and model research are implemented; scheduled reports and a separate
durable research worker remain future work. Original BMW files are excluded from deployment, so
hosted downloads of those originals are unavailable. See the [frontend guide](../../frontend/README.md)
for setup and validation boundaries.
