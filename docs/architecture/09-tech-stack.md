# Tech stack

> Status: `draft` · Last updated: 2026-10-10 (web search through the LLM, see decision 0009)

Kept boring on purpose — a hackathon is not the place to debug infrastructure.

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | Its explicit interrupt-for-human-input pattern maps directly onto the per-step PM gates in [`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md) — one `interrupt()` per `Step`, not one at the end, plus a planner node where the orchestrator chooses the agents. Its Postgres checkpointer stores run state in the same Supabase database (use the direct or session-pooler connection string, not the transaction pooler) |
| LLM | Every agent is LLM-backed. Currently the OpenAI API (key in `.env`); the provider is a config choice and Claude remains an option | Extraction, cluster labeling, requirement drafting, scoring rationale, Critic verification, answering over retrieved evidence. Answers may only cite retrieved rows |
| Web research | The LLM's built-in web search tool (OpenAI Responses API `web_search`), for now | No extra search API key or service. Sources are built from the tool's citation annotations, not from model-written text; source-trust tagging is applied at ingest time. A dedicated search API (Tavily/Brave) stays an option, see [decision 0009](../decisions/0009-web-search-through-the-llm.md) |
| PDF parsing | `pdftotext -layout` (poppler) for text; pdfplumber / vision-LLM still planned for the equipment tables | Text extraction works (the catalogs have real text). Reliable ■/□ column mapping needs table-aware extraction or a vision pass — not built yet |
| Excel | openpyxl (+ psycopg for loading) | Loaders in `backend/app/ingest/`; the customer-study cross-tabs need a custom parser |
| Storage | Supabase (managed Postgres) + pgvector 0.8 | One database for both relational entities (`Finding`, `Requirement`, `AuditEvent`, …) and embeddings — keeps traceability joins simple instead of reconciling two stores. Schema is live: see `supabase/migrations/`. RLS is on for every table with no policies yet, so only the backend (service role / direct connection) can read or write; the frontend goes through the API |
| Embeddings | OpenAI `text-embedding-3-small` (1536 dims, cosine, HNSW) | Key in `.env` as `OPENAI_API_KEY`. Only `finding.text` and `chunk.content` are embedded; option codes and sales numbers stay exact, un-embedded data. Changing the model means re-embedding and altering the column — see [decision 0004](../decisions/0004-supabase-and-openai-embeddings.md) |
| API | FastAPI (`backend/app/api`), served by uvicorn | Thin HTTP layer over the knowledge layer and, later, the orchestrator. See [`12-repo-structure.md`](12-repo-structure.md) |
| Frontend | Vite + React + TypeScript + Tailwind v4 + shadcn/ui, BMW tokens from `design.md` (`frontend/`) | Chat thread with step cards (Accept / Edit / Retry / Reject) and a plan strip, evidence panel with citations, score breakdown, audit timeline |
| Deploy | Docker-compose / Vercel demo instance; Supabase hosts the database and raw-file storage | Single environment for the demo |
