# 0012 — The planner model proposes agents; code validates, orders and completes the plan

> Date: 2026-10-12 · Status: accepted

## Context

Decision 0005 made the orchestrator choose which agents a request needs. A model can judge that from the wording,
but its output cannot be trusted to respect the pipeline: it can invent agents, repeat them, order them wrongly or
skip a prerequisite (Prioritization without Drafting). Only one agent exists today, so a plan must also say what
cannot run yet.

## Decision

1. **An LLM proposes, code decides.** The model returns agents with reasons and any scope it finds. `normalize_plan`
   drops unknown names, deduplicates, orders by pipeline stage and adds missing prerequisites, marked as such.
2. **The catalog is the single list of agents** (`orchestration/catalog.py`) with a stage, a description for the model
   and an `available` flag. Plans may include unavailable agents, flagged in the plan and in a note, so the PM sees what
   the question needs; they cannot run until built.
3. **Scope is optional**: no line or market means `ALL`. The system is not tied to one slice.
4. **Plan edits by the PM are validated, not completed**: an invalid edit is refused with the reason (422), and edits are
   refused once any step has started (409).
5. **No silent fallback.** A planner failure gives 503 and stores nothing. `PLANNER=rules` is an explicit local setting.
6. **Thread order uses a sequence number** (`message.seq`), because one request writes several messages in a single
   transaction and `created_at` is identical for all of them. This was found when tests intermittently returned the plan
   before the request.

## Consequences

- Checked on six sample requests with the real model: topic routing needed explicit guidance in the prompt (an option
  availability question first returned no agents) and now routes correctly. The prompt's topic-to-agent list must be kept
  in step with the catalog when agents are added.
- The planner is a model call per request: a few seconds and a small cost.
- Planning is separate from running. Starting a plan, the step runner and the agents are still to build.

See [`../architecture/02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md).
