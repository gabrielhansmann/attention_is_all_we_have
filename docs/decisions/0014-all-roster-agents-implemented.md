# 0014 — All roster agents exist as modules; the interpretations they needed

> Date: 2026-10-10 · Status: accepted

## Context

Only the Market & Trend Agent existed. The other roster agents in `architecture/01-agents.md` were built in
parallel, one module each under `backend/app/agents/`, following the Market & Trend Agent's shape (result
dataclass, `build_result`, `summarize`, `store_result`, `--dry-run`). The docs left several points open or
assumed data and tables that do not exist, so each agent had to pick an interpretation.

## Decision

1. **Every catalog agent is `available`.** `available` means the module exists. The step runner that calls them
   is [decision 0015](0015-step-runner-and-step-output-on-the-step.md).
2. **A citation is copied from the evidence, never written by the model.** Models reference evidence by index or
   finding id; code drops anything that does not resolve. Numbers (volumes, shares, scores, deltas) are computed
   in code. Sales & Portfolio, Prioritization, Documentation, Delta / Tracking and the Critic use no model at all.
3. **Sample size on a feedback finding is the number of cited comments**, with the polarity total in scope as
   `sample_base`. The knowledge tools give no exact count per topic.
4. **There is no measured option take rate.** `sales_volumes.xlsx` is line × market × year. The Sales & Portfolio
   Agent reports the share of catalog variants where an option is standard and labels it a proxy; Prioritization
   uses it for `business_signal` and lists it as thin evidence.
5. **Competitor runs as one step** (doc 10's fallback, not its three-step proposal). Doc 10's tables are not
   created: anchor profile, bands, rival set and comparison cells live in the result and in
   `step.structured_output_refs`. `competitor_weakness` is not emitted because the `finding.signal_type`
   constraint does not allow it.
6. **Critic thinness rules are caps, not a step down.** A web finding is capped at `Unverified` for
   `forum_social`, and at `Interpreted` when the trust tier is unknown or a single source is uncorroborated.
   File-backed findings are not downgraded. This overrides the Market & Trend Agent's own `oem` → `Verified` for a
   lone OEM page. Synthesis output (clusters, requirements, scores) must reference findings passed in as
   `known_findings`. When the retry budget is used up, unsupported claims are dropped and reported, and the
   pruned output goes to review.
7. **Prioritization components are derived by constants in the module**, tuned so the `R-2031` example in doc 06
   reproduces 0.49. Effort maps to low 0.05, medium 0.50, high 0.95. A missing input counts as zero, costs 0.10
   confidence and is listed. The tier is a `proposed_tier` on the score and is never written to the requirement.
8. **Delta / Tracking matches by word overlap** and decides contradiction from signal type and sentiment; an
   embedding similarity can be injected. It is not a plannable chat step, so it is not in the catalog. Flags are
   stored as audit events.
9. **Each agent has its own out-of-scope pattern.** The Market & Trend one matches "fine" and "mandatory", which
   misfire on customer comments and reviews.
10. The Market & Trend Agent's step insert now sets `position` (NOT NULL since the chat migration).

## Consequences

- The agents are tested with fixtures only (175 backend tests). No `store_result` has run against the live
  database, and no model call of the new agents has run live.
- Open against the docs, to resolve when accepted output is persisted to its tables:
  - Drafting stores requirements at `draft` in its own step; doc 05 says a requirement enters the lifecycle when
    the Documentation step is accepted. A retry leaves old `requirement_finding` links behind.
  - The dossier re-embed inserts a `source` of type `dossier`, which the current check constraint rejects. It needs
    a migration and a rule for whether dossier chunks are citable.
  - `score` has no column for the weight vector or breakdown; they are kept in the audit event and the step.
  - Stage-1 finding dataclasses carry no `id`; the later agents need the stored finding ids passed in.
  - Drafted requirements carry no `effort_proxy` or themes, so a score assumes medium effort and says so.
- The helpers duplicated between agents (`ensure_step`, evidence/citation types) should move to one shared module.

See [`../architecture/01-agents.md`](../architecture/01-agents.md) and
[`../architecture/06-prioritization.md`](../architecture/06-prioritization.md).
