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
