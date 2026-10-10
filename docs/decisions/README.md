# Decision log

Dated, append-only. Add a new numbered file rather than editing an old one when a decision
changes — note the supersession in the new file and update the old one's status line.

| # | Decision | Status |
|---|---|---|
| [0001](0001-two-tier-pdf-ingestion.md) | Two-tier PDF ingestion instead of naive text extraction | accepted |
| [0002](0002-stepwise-agent-approval-chain.md) | Gate every agent step, not just the drafted requirement and its score | superseded by 0018 |
| [0003](0003-critic-agent-and-agent-split.md) | Add a Critic Agent; split Competitor from Market/Trend | accepted |
| [0004](0004-supabase-and-openai-embeddings.md) | Supabase Postgres + pgvector for storage; OpenAI `text-embedding-3-small` for embeddings | accepted |
| [0005](0005-chat-entry-and-orchestrator-planned-steps.md) | Chat entry point; orchestrator plans the agents; accepting a step starts the next | superseded by 0018 |
| [0006](0006-raw-tables-and-cited-pdf-chunks.md) | Load Excel as raw relational tables; chunk PDFs per page with real citations | accepted |
| [0007](0007-option-availability-and-ontology-seed.md) | Parse equipment tables by position; seed the ontology from the feedback labels | accepted |
| [0008](0008-knowledge-layer-normalization-and-retrieval.md) | Normalize all evidence to one vocabulary; one retrieval interface that returns citations | accepted |
| [0009](0009-web-search-through-the-llm.md) | Web search runs through the LLM's built-in search tool for now, not a separate search API | accepted |
| [0010](0010-frontend-backend-repo-structure.md) | Split the repository into a FastAPI backend and a React frontend | accepted |
| [0011](0011-local-demo-frontend-and-vercel.md) | Deliver a local demo PM workspace and Vercel hosting alongside the backend Evidence browser | superseded by 0017 |
| [0012](0012-planner-proposes-code-validates.md) | The planner model proposes agents; code validates, orders and completes the plan | superseded by 0018 |
| [0013](0013-frontend-uses-only-the-backend-api.md) | The frontend reaches data only through the backend API; live mode sits beside the demo | accepted |
| [0014](0014-all-roster-agents-implemented.md) | All roster agents exist as modules; the interpretations they needed | accepted |
| [0015](0015-step-runner-and-step-output-on-the-step.md) | The step runner: agents run in the background, output is kept on the step | accepted |
| [0016](0016-backend-owned-authentication.md) | Backend-owned users and server-side sessions protect the whole API | accepted |
| [0017](0017-minimal-live-only-frontend.md) | Minimal, live-only frontend: the demo workspace and its fixtures are removed | accepted |
| [0018](0018-orchestrator-decides-in-an-agentic-loop.md) | The orchestrator chooses agents in a loop from each result; nobody approves a step | accepted |
| [0019](0019-orchestration-loop-runs-on-langgraph.md) | The orchestration loop runs as a LangGraph graph with a Postgres checkpointer, so runs survive a restart | accepted |
| [0020](0020-source-viewer-for-citations.md) | Citations open a source viewer: the passage in context and the original file | accepted |
| [0021](0021-rounded-chat-first-frontend.md) | Chat-first frontend with rounded components and soft elevation | accepted |
| [0022](0022-requirement-register-and-process-views.md) | Requirement register, PM decisions, tracking checks and the requirements, tracking and dossier views | accepted |
