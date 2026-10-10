# PM control & traceability

> Status: `draft` · Last updated: 2026-10-10

The two properties the brief weighs most: the PM decides, and every decision can be traced.
Derived from
[`02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md),
[`01-agents.md`](../architecture/01-agents.md#the-critic-agent) and
[`07-audit-trail.md`](../architecture/07-audit-trail.md).

## Step-by-step control

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-HL-01 | Start a run from a scope (vehicle line, market) and optionally a question in plain language. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#worked-example--what-features-would-we-need-to-stay-competitive-in-the-us-market) |
| FR-HL-02 | Start the first agent only after the PM confirms the plan. Acceptance starts the next step automatically; rejection advances only with explicit permission to continue with a gap. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-unit-of-work-a-step), [ADR 0005](../decisions/0005-chat-entry-and-orchestrator-planned-steps.md), [ADR 0022](../decisions/0022-project-review-and-live-step-controls.md) |
| FR-HL-03 | Let the PM select situation-analysis agents before execution; run them sequentially in canonical pipeline order. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-full-chain) |
| FR-HL-04 | Present every finished step with a plain-language summary: what was looked at, what was found with citations, how confident the agent is, what is missing, what was set aside as out of scope. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#human-readable-output-every-time) |
| FR-HL-05 | Offer accept, summary edit, retry with a steering note and reject on successful output in review. Failed output permits retry or reject, never acceptance. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-four-actions-same-verbs-as-everywhere-else) |
| FR-HL-06 | After a rejection, let the PM continue without that agent's contribution or abort the run; continuing marks everything downstream as having a coverage gap. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-four-actions-same-verbs-as-everywhere-else) |
| FR-HL-07 | Check every agent output for unsupported claims before the PM sees it, and send it back to the agent to cite or drop them. | M | [01](../architecture/01-agents.md#the-critic-agent), [ADR 0003](../decisions/0003-critic-agent-and-agent-split.md) |
| FR-HL-08 | Lower the evidence level of claims that are cited but thin — single source, no corroboration, low trust tier. | M | [01](../architecture/01-agents.md#the-critic-agent) |
| FR-HL-09 | Never change a requirement's status, tier or scope without a PM action. | M | [01](../architecture/01-agents.md) |

**FR-HL-07** — if the agent still cannot support a claim after its retry, the step reaches the PM
with the claim removed and the removal noted in the summary; it does not loop indefinitely.

## Traceability

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-TR-01 | From any requirement, reach each supporting finding and from there the exact place in the source — cell, page, URL, post. | M | [04](../architecture/04-data-model.md) |
| FR-TR-02 | From any source or finding, show which clusters and requirements it supports. | S | [04](../architecture/04-data-model.md) |
| FR-TR-03 | Record every change to a step, finding, cluster, requirement or score with who or what made it, when, the state before and after, and the reason. | M | [07](../architecture/07-audit-trail.md#schema) |
| FR-TR-04 | Require a reason for every PM decision that changes a status; the decision cannot be saved without one. | M | [07](../architecture/07-audit-trail.md#schema) |
| FR-TR-05 | Make the record append-only: an entry cannot be edited or deleted. | M | [07](../architecture/07-audit-trail.md) |
| FR-TR-06 | Show the history of a requirement and of a run as a timeline, distinguishing agent actions from PM actions. | M | [07](../architecture/07-audit-trail.md#worked-example-r-2031) |
| FR-TR-07 | Let the PM override the evidence level of a finding; the override is recorded and applied to that source's grading from then on. | S | [03](../architecture/03-ingestion.md#tier-2--semantic-narrative-text-web-content) |
| FR-TR-08 | Record a committee decision as one entry with its participants and rationale, against one accountable PM. | C | [05](../architecture/05-requirement-lifecycle.md#committee--board-mode) |

**FR-TR-01** — this holds for all three input families. For a social media finding the PM lands on
the post or its stored snapshot (`FR-IN-15`), with personal data masked (`FR-IN-17`).
