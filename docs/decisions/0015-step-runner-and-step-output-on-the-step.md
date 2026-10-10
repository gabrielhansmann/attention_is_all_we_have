# 0015 — The step runner: agents run in the background, output is kept on the step

> Date: 2026-10-10 · Status: accepted; the PM actions and the start call were replaced by the orchestrator loop in [0018](0018-orchestrator-decides-in-an-agentic-loop.md)

## Context

Plans were stored but nothing ran them (decision 0012), and the agents existed only as modules (decision 0014).
The agents' own `store_result` functions write findings, clusters and requirements straight to their tables and
set the step to `awaiting_review`, each with a different signature, without the Critic, and before the PM has
accepted anything. Stage-1 findings also carry no id, which the later agents need to cite them.

## Decision

1. **`orchestration/runner.py` runs a plan.** `POST /api/runs/{id}/start` is the PM confirming the plan; it starts the
   first step and locks the plan. `POST /api/steps/{id}/accept | retry | reject | edit` are the four actions. Accept
   starts the next planned step; after the last one the run is `completed` and a `final_result` message is written.
2. **The agent runs after the response is sent** (a FastAPI background task with its own connection). The call
   returns with the step `running`; the client polls the conversation until the step card arrives. An agent run
   takes from seconds to minutes and no transaction is held open while it works.
3. **Every agent call goes through the Critic** (`review_with_retries`, one automatic retry). The accepted
   findings of earlier steps are passed as `known_findings`, so a cluster, requirement or score can only rest on
   evidence the PM accepted.
4. **A step's output is JSON on the step** (`step.structured_output_refs = {output, critic}`), after the Critic's
   adjustments, and copied into the step card's payload. Later agents read the accepted steps' output from there.
   The runner does not call the agents' `store_result`: nothing is written to `finding`, `cluster`, `requirement`
   or `score` by a run yet.
5. **The runner gives every finding an id** (stable, from locator and text) when the agent did not.
6. **One adapter per agent** (`orchestration/agents.py`) turns the run's scope, request, steering and accepted
   output into that agent's call. The PM's steering note and the Critic's instruction are appended to the task of
   the agents that use a model. Prioritization is deterministic; a note such as `business_signal=0.35` re-weights it.
7. **An agent that fails still ends in `awaiting_review`**, with a card that says it failed and no output, so the
   PM can retry or reject. There is no `failed` state.
8. **Reject asks for the choice in the same call** (`proceed`): go on with a coverage gap, or abort the run.
9. **Edit rewrites the summary only**, not the structured output. The before/after is the audit event.
10. **The final result** is the Documentation Agent's dossier when that step was accepted, otherwise the accepted
    step summaries in order, with rejected agents listed as coverage gaps.
11. The Critic accepts a `[finding id]` marker of a known finding as a citation, because the dossier cites that way.

## Consequences

- Evidence produced by a run is not searchable in the knowledge layer and draft requirements do not reach the
  backlog tables until accepted output is persisted. That is the next piece, together with the open points in
  decision 0014 (dossier source type, score breakdown columns).
- If the server stops while an agent runs, the step stays `running` and the run is stuck; there is no recovery yet.
- A background task is in-process: fine for the demo, not for several workers. LangGraph with a checkpointer
  (doc 09) remains the intended replacement.
- The frontend's live mode (decision 0013) shows the plan and plan editing only. It does not call the start and step
  endpoints yet, and its note that agents do not run is now out of date.
- Audit actions added: `step_started`, `step_finished`, `step_failed`, `step_accepted`, `step_edited`,
  `step_retried`, `step_rejected`, `run_completed`, `run_aborted`, and the Critic's `evidence_level_downgraded` and
  `claim_dropped`, all filed under the step or the run.

See [`../architecture/02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md).
