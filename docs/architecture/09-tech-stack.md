# Tech stack

> Status: `draft` · Last updated: 2026-10-10

Kept boring on purpose — a hackathon is not the place to debug infrastructure.

| Layer | Choice | Why |
|---|---|---|
| Orchestration | LangGraph | Its explicit interrupt-for-human-input pattern maps directly onto the per-step PM gates in [`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md) — one `interrupt()` per `Step`, not one at the end |
| LLM | Claude | Extraction, cluster labeling, requirement drafting, scoring rationale, Critic verification |
| Web research | Search API tool-call (Tavily/Brave) | Source-trust tagging applied at ingest time, not after the fact |
| PDF parsing | pdfplumber / unstructured, vision-LLM fallback | Tables parsed deterministically; complex/scanned layouts fall back to a vision pass |
| Excel | pandas / openpyxl | Nothing fancier needed |
| Storage | Postgres + pgvector | One database for both relational entities (`Finding`, `Requirement`, `AuditEvent`, …) and embeddings — keeps traceability joins simple instead of reconciling two stores |
| API | FastAPI | — |
| Frontend | React + shadcn/ui | Step-by-step run view (stepper/Kanban hybrid), evidence panel, score breakdown, audit timeline |
| Deploy | Docker-compose / Vercel demo instance | Single environment for the demo |
