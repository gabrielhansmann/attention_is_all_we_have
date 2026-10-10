# 0018 — The orchestrator chooses agents in a loop; nobody approves a step

> Date: 2026-10-14 · Status: accepted (the hand-written loop became a LangGraph graph in [0019](0019-orchestration-loop-runs-on-langgraph.md)) · Supersedes [0002](0002-stepwise-agent-approval-chain.md), [0005](0005-chat-entry-and-orchestrator-planned-steps.md) and [0012](0012-planner-proposes-code-validates.md); changes the run model of [0015](0015-step-runner-and-step-output-on-the-step.md)

## Context

Decisions 0002 and 0005 had the orchestrator plan a fixed list of agents up front, and made the PM start the plan,
edit it, and accept, edit, retry or reject every agent result before the next agent ran. In use, the PM was doing the
orchestrator's job: choosing agents, deciding whether a result was enough, and clicking through steps. The intended
behaviour is the opposite: the orchestrator decides which agents a request needs, reads each answer, and decides
whether it needs more, in a loop. The person asks and reads the result.

## Decision

1. **A loop, not a plan.** After a request is stored, the backend runs `orchestration/loop.py` in the background. It
   asks the orchestrator for a decision (`call <agent>` or `finish`), runs that one agent, and asks again with the
   result in front of it. The model sees each earlier agent's summary, finding count and whether it succeeded.
2. **The model proposes, code decides** (carried over from 0012). `check_call` refuses an unknown agent, an agent
   not built, one that already ran, or a later-stage agent whose earlier stages have no successful result. A refusal
   goes back to the model as a note; after more than two refusals in a row the loop stops and keeps what it has.
3. **No person approves anything.** The plan, start, edit-plan, accept, edit, retry and reject endpoints are removed.
   A step is created `running` when the orchestrator decides, and ends `accepted` (the agent answered and the Critic
   passed it) or `rejected` (the agent failed; the reason is on the step and the orchestrator is told). The Critic stays
   inside every step as the automatic reviewer. `awaiting_review` and `planned` remain in the database constraint but
   nothing enters them.
4. **Budget and safety.** At most 8 agent calls per request. A failed agent never hangs the run. If the orchestrator
   model fails after some agents succeeded, the run completes with what they found and says so; if before, it aborts.
   An unexpected error aborts the run with a note instead of leaving it `in_progress`.
5. **Transparent.** Each decision is a `system_note` message with the agent and the reason, followed by the agent's
   step card, then the final result. The audit log records `run_started`, `step_started` (with the reason),
   `step_finished` or `step_failed`, and `run_completed`, all by the orchestrator; the requester is on `run_started`.
6. **One request at a time per conversation** (409 otherwise); a follow-up starts a new run once the last one ended.
7. `PLANNER` becomes `ORCHESTRATOR` (`llm` or `rules`). The `rules` orchestrator is a keyword stand-in for tests and
   local work without a key: it calls a fixed target set and does not react to results.

## Consequences

- The step output rules of 0015 stand: later agents receive only output from accepted steps.
- A run can take minutes and runs in the API process. This decision left a restart stranding the run; decision 0019 fixes that with a LangGraph checkpointer.
- The "per-step human review" that 0002 argued for is gone by request. Requirement-level approval in
  [`05-requirement-lifecycle.md`](../architecture/05-requirement-lifecycle.md) is unchanged: drafts still enter at `Draft`.
- The frontend shows the thread read-only and refreshes while a run is in progress.
