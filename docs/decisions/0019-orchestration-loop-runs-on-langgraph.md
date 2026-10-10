# 0019 — The orchestration loop runs as a LangGraph graph with a Postgres checkpointer

> Date: 2026-10-14 · Status: accepted · Builds on [0018](0018-orchestrator-decides-in-an-agentic-loop.md); reverses its "LangGraph is not used"

## Context

Decision 0018 made the orchestrator choose agents in a loop, written by hand in `loop.py`. Its main weakness: the loop
ran in the API process, so a restart left the run `in_progress` for ever. LangGraph was planned from the start
(decisions 0002, 0004, 0005) for per-step human gates; those are gone, but its checkpointer solves the restart problem.

## Decision

1. **The loop is a `StateGraph`** (`orchestration/loop.py`): nodes `decide`, `validate`, `run_agent`, `finish`, with
   conditional edges. The decision model, `check_call`, `runner.execute_step` and the service functions are unchanged;
   they are the node bodies.
2. **The graph state is control flow only**: the pending call, the refusals shown to the model, why the loop is stopping.
   What happened is in `pipeline_run`, `step` and `message`; `decide` rebuilds its history from the tables. There is one
   record of a run, and nothing the UI shows is read from a checkpoint.
3. **Checkpointer: `PostgresSaver`**, thread id = run id, on its own connection to the project database. The tables come
   from migration `20261014_langgraph_checkpoints.sql` (the library's schema, RLS on). The app never calls `setup()`,
   so it runs no DDL.
4. **Resume on start.** The API's lifespan finds runs still `in_progress` and continues each from its last checkpoint
   in its own thread. A run with steps but no checkpoint (from before this decision) is left alone; a run with no steps
   and no checkpoint is started fresh.
5. **Safe to run twice.** `run_agent` reuses a step still `running` (the process died mid-agent: the agent runs again
   in the same step) and never creates a second step for an agent that already has one. A session advisory lock on the
   run id stops two processes, or a restart overlapping its predecessor, from driving the same run.
6. **Tests** use `InMemorySaver` through a dependency override; one test uses the real Postgres checkpointer and cleans
   up after itself.

## Consequences

- New dependencies: `langgraph` and `langgraph-checkpoint-postgres`. The checkpointer needs the direct or session-pooler
  connection string (not the transaction pooler), which `SUPABASE_DB_URL` already is.
- A run still executes in the API process. What changed is that a restart no longer loses it. An agent that was mid-call
  repeats that one call (model and web cost). A separate worker or queue is still not built.
- Dropping the checkpoint tables loses only the ability to resume runs in progress.
- Parallel fan-out of the stage 1 agents (LangGraph's `Send`) and human `interrupt()` are now possible and not used.
  Fan-out would need the orchestrator to return several calls in one decision.
