# Decision log

Dated, append-only. Add a new numbered file rather than editing an old one when a decision
changes — note the supersession in the new file and update the old one's status line.

| # | Decision | Status |
|---|---|---|
| [0001](0001-two-tier-pdf-ingestion.md) | Two-tier PDF ingestion instead of naive text extraction | accepted |
| [0002](0002-stepwise-agent-approval-chain.md) | Gate every agent step, not just the drafted requirement and its score | accepted |
| [0003](0003-critic-agent-and-agent-split.md) | Add a Critic Agent; split Competitor from Market/Trend | accepted |
| [0004](0004-supabase-and-openai-embeddings.md) | Supabase Postgres + pgvector for storage; OpenAI `text-embedding-3-small` for embeddings | accepted |
| [0005](0005-chat-entry-and-orchestrator-planned-steps.md) | Chat entry point; orchestrator plans the agents; accepting a step starts the next | accepted |
| [0006](0006-raw-tables-and-cited-pdf-chunks.md) | Load Excel as raw relational tables; chunk PDFs per page with real citations | accepted |
| [0007](0007-option-availability-and-ontology-seed.md) | Parse equipment tables by position; seed the ontology from the feedback labels | accepted |
| [0008](0008-knowledge-layer-normalization-and-retrieval.md) | Normalize all evidence to one vocabulary; one retrieval interface that returns citations | accepted |
| [0009](0009-web-search-through-the-llm.md) | Web search runs through the LLM's built-in search tool for now, not a separate search API | accepted |
| [0010](0010-frontend-backend-repo-structure.md) | Split the repository into a FastAPI backend and a React frontend | accepted |
| [0011](0011-local-demo-frontend-and-vercel.md) | Deliver a local demo PM workspace and Vercel hosting alongside the backend Evidence browser | accepted |
| [0012](0012-planner-proposes-code-validates.md) | The planner model proposes agents; code validates, orders and completes the plan | accepted |
