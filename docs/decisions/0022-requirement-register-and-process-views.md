# 0022 — A requirement register, PM decisions and the tracking loop become product features

> Date: 2026-10-10 · Status: accepted · Builds on [0014](0014-all-roster-agents-implemented.md) and [0018](0018-orchestrator-decides-in-an-agentic-loop.md); implements the lifecycle in [`architecture/05`](../architecture/05-requirement-lifecycle.md)

## Context

BMW's process slide ends in prioritization, documentation and requirements tracking. The agents for those stages
existed (decision 0014), but their output lived only as JSON on a step and as text in the chat. The PM could not
see requirements as a list, approve one, re-rank by what matters to them, or have a requirement watched over time.
Decision 0014 also left open that drafted requirements and scores are not persisted, and that the Delta / Tracking
Agent was not reachable from the product.

## Decision

1. **`requirement_register`** (migration `20261015`) holds a snapshot of each drafted requirement and its score,
   filed when a run completes (`register.sync_run`, called from `runner._complete`). It stores the cited statements as
   JSON, so it does not depend on stage-1 findings having been written to the `finding` table (the open problem in
   0014). A requirement the PM has decided on is never overwritten by a later run. The original `requirement` and
   `score` tables stay for the pipeline-style persistence the agents' own `store_result` writes.
2. **PM decisions** follow doc 05: approve (to tracked), reject, challenge, supersede, reopen, and acknowledge (clear
   tracking flags). Reject, challenge and supersede need a reason. Each decision is an audit event on the requirement.
   `draft` is shown as "Needs review"; the separate `pm_review` state is accepted but not entered, because nothing
   moves a requirement there automatically.
3. **Tracking** (`tracking.check`): for every tracked requirement, search customer feedback with its title, give the
   hits to the Delta / Tracking Agent as the new batch and its drafting evidence as the existing evidence, and store
   the flags as audit events. A flag stays open until the PM acknowledges the requirement. The agent still never
   changes a status. A check is started by the PM; there is no scheduler yet. The provided data has no ingestion
   dates, so "new" means "not already cited", and the stale check is skipped for undated evidence.
4. **Frontend**: Requirements (review and approve; a Priorities tab with weight sliders, a ranked list and a
   customer-against-business map), Tracking, and Dossiers, plus a five-step strip (Research, Review, Prioritize,
   Track, Document) on each page and a "Review N requirements" button under a chat result. The slider what-if
   recomputes the doc 06 formula in the browser from the stored components and is never saved.
5. API: `GET /api/requirements`, `GET /api/requirements/{id}`, `POST /api/requirements/{id}/decision`,
   `GET /api/tracking`, `POST /api/tracking/check`, `GET /api/dossiers`. All sit in the protected router.

## Consequences

- The stage-1 findings behind a requirement are read back from the run's step output, so a requirement's citations
  open in the source viewer. A requirement from a run whose step output was removed would show text without sources.
- Not done: a scheduled tracking run, moving a flagged requirement to `pm_review` automatically, editing a requirement's
  text or metric in the UI, the Delta Agent as a chat step, and candidate-metric alternatives ("600 or 700 mi?").
- The two old chat and auth tests that depend on rows already in the live database still fail; they did before.
