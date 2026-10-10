# Tech stack

> Status: `building` · Last updated: 2026-10-10 (local demo frontend and Vercel, see decision 0011)

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
| API | FastAPI (`backend/app/api`), served by uvicorn | Evidence endpoints are implemented. Authentication and live orchestration remain future work; see [`12-repo-structure.md`](12-repo-structure.md) |
| Frontend | React + TypeScript + Vite; Radix primitives and variant-based components following the shadcn pattern | Implemented in `frontend/`: scoped overview, targets, portfolio, review gates, evidence, reports, and local decision history. BMW tokens, self-hosted Inter, Phosphor icons; see [decision 0011](../decisions/0011-local-demo-frontend-and-vercel.md) |
| Frontend persistence | Browser local storage (demo only) | Illustrative fixtures, local edits and previews, JSON/CSV export. No shared or immutable server persistence |
| Deploy | Static Vercel frontend; Supabase hosts the backend database | Deploy `frontend/` as Vite. Python services are separate and are not deployed with this frontend. Docker-compose remains a possible future backend option |

The deployed PM workspace is a working local demo, not a live agent client. It does not query Supabase,
perform LLM/web research, parse binary uploads, or schedule weekly reports. Service credentials
remain backend-only. See the [frontend guide](../../frontend/README.md) for setup and verification.

The backend-connected Evidence browser from the repository restructure is retained in the local
frontend, reached from Evidence library. Vite proxies its `/api` calls to FastAPI. It can also be
enabled in another deployment with `VITE_LIVE_EVIDENCE=true` once that origin serves the API.
The current static Vercel demo has no backend and keeps this option disabled.
