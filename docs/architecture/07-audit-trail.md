# Audit trail

> Status: `draft` · Last updated: 2026-10-10 (database workspace; [decision 0023](../decisions/0023-database-backed-workspace.md))

One append-only `AuditEvent` log underlies everything: every orchestrator plan and plan change, every `Step`
start/accept/edit/retry/reject
inside a run (a step "starts" automatically when the previous one is accepted, so the start event
records which acceptance triggered it), and requirement status reviews afterward. Broader content editing/versioning remains planned.
Run and step actions write these events. Requirement status reviews now write `requirement_status_changed`
with the signed-in actor, before/after status and required reason in the same transaction as the update.
Overview and Reports read the database trail; no mutable browser decision history is generated.

## Schema

`id, entity_type, entity_id, actor, action, before, after, rationale, timestamp`

- `actor` — an agent name (`PrioritizationAgent`) or a PM identity. Never ambiguous about who/what.
- `rationale` — required for acceptance, retry and rejection. Plan confirmation records a fixed confirmation
  reason; summary edits accept an optional note at the API, while the live UI asks for one. The UI will not
  commit a status change
  without it (see [`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md)).
- `before` / `after` — enough of the record's state to render a diff, not the whole object.

Step and run actions as written by the runner: `step_started`, `step_finished`, `step_failed`, `step_accepted`,
`step_edited`, `step_retried`, `step_rejected`, `run_started`, `run_completed`, `run_aborted`, plus the Critic's
`evidence_level_downgraded` and `claim_dropped` filed under the step.

## Worked example: R-2031

This is an illustrative audit trail, not a live database record. The example requirement (linked findings,
assumptions, score breakdown) is in
[`06-prioritization.md`](06-prioritization.md#worked-example). Its audit trail:

| Timestamp | Actor | Action | Rationale |
|---|---|---|---|
| 2026-01-14 09:02 | RequirementsDraftingAgent | Created R-2031 — `draft` | "3 corroborating findings clustered under Interior/Comfort::Seat Ventilation" |
| 2026-01-14 09:03 | PrioritizationAgent | Scored R-2031 — composite 0.49, Tier 2, weights v1.3 | — |
| 2026-01-16 14:51 | PM | Edited acceptance criteria: 140s → 75s | "Align with fleet thermal-comfort benchmark, not a customer time-guess" |
| 2026-01-16 14:52 | PM | Approved — `draft` → `tracked` | "Accept the direction pending protocol validation" |
| 2026-04-02 03:10 | DeltaAgent | Flagged new finding F-517 (competitor launch review) | "New evidence available, re-review suggested" |
| 2026-04-03 10:20 | PM | Reviewed, kept `tracked` | "New evidence reinforces the existing decision, no scope change" |

Every field the brief's audit-trail deliverable asks for falls out of this table directly: who or
what initiated each change, when, and the documented rationale — queryable, not a screenshot of a
decision.
