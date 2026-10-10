# 0005 — Chat entry point; orchestrator plans the agents; accept starts the next one

> Date: 2026-10-10 · Status: superseded by [0018](0018-orchestrator-decides-in-an-agentic-loop.md) · Supersedes part of [0002](0002-stepwise-agent-approval-chain.md)

## Context

Decision 0002 gated every agent step, but kept all five research agents as visible cards that the
PM launched by hand, in any order, with a separate "Run" click per agent. In practice the PM wants
to ask a research question in natural language and have the system work out which agents are
needed, then review each agent's answer in turn.

## Decision

1. **Chat is the entry point.** A PM starts a new chat with a research request; each request
   creates a `PipelineRun` tied to that conversation.
2. **The orchestrator plans.** It selects the agents needed for the request, shows the plan with a
   reason per agent, and the PM can edit it before the first agent starts. The orchestrator may
   revise the remaining plan as results come in; changes are announced in the chat.
3. **Accept starts the next agent.** The separate manual "Run" click (the `awaiting_launch` state)
   is removed. Steps run strictly one at a time; the next needed agent starts when the previous one
   is accepted. This replaces the part of 0002 that said accepting only unlocks the next step.
4. **Push back in the chat.** Edit / Retry (steering note) / Reject remain available at every step;
   Retry is a reply on the step's thread.
5. **No final result before all needed agents are accepted.** Every claim in it carries a citation
   to a retrieved finding (source + locator).
6. **Not every agent runs every time.** Drafting, Prioritization, and Documentation are added only
   when the request asks for requirements.

## Consequences

- Fewer clicks than 0002 (one per step, not two), and the PM still reviews every agent output
  before the next one starts.
- The orchestrator is now a real planning component (an LLM call that chooses agents), not just a
  state machine. Its choices must be visible and overridable, which is why the plan is shown and
  editable.
- Step states become `planned → running → awaiting_review → accepted | rejected`. This needs a
  schema migration: `step.status` currently allows `queued` / `awaiting_launch`, and there are no
  `conversation` / `message` tables yet. **Applied in `supabase/migrations/20261011_chat_tables.sql`.**
- LangGraph still maps well: one `interrupt()` per step, plus a planner node at the start.

See [`../architecture/02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md).
