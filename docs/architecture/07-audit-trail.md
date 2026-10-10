# Audit trail

> Status: `draft` · Last updated: 2026-10-10 (plan events)

One append-only `AuditEvent` log underlies everything: every orchestrator plan and plan change, every `Step` start/accept/edit/retry/reject
inside a run (a step "starts" automatically when the previous one is accepted, so the start event
records which acceptance triggered it), and every requirement-level approve/edit/reject/challenge afterward. Nothing updates
a record in place without also writing one of these.

## Schema

`id, entity_type, entity_id, actor, action, before, after, rationale, timestamp`

- `actor` — an agent name (`PrioritizationAgent`) or a PM identity. Never ambiguous about who/what.
- `rationale` — required for every PM-initiated action. The UI will not commit a status change
  without it (see [`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md)).
- `before` / `after` — enough of the record's state to render a diff, not the whole object.

## Worked example: R-2031

The full requirement (linked findings, assumptions, score breakdown) is in
[`06-prioritization.md`](06-prioritization.md#worked-example). Its audit trail:

| Timestamp | Actor | Action | Rationale |
|---|---|---|---|
| 2026-01-14 09:02 | RequirementsDraftingAgent | Created R-2031 — `draft` | "3 corroborating findings clustered under Interior/Comfort::Seat Ventilation" |
| 2026-01-14 09:03 | PrioritizationAgent | Scored R-2031 — composite 0.49, Tier 2, weights v1.3 | — |
| 2026-01-16 14:51 | PM | Edited acceptance criteria: 140s → 75s | "Align with fleet thermal-comfort benchmark, not a customer time-guess" |
| 2026-01-16 14:52 | PM | Approved — `draft` → `tracked` | — |
| 2026-04-02 03:10 | DeltaAgent | Flagged new finding F-517 (competitor launch review) | "New evidence available, re-review suggested" |
| 2026-04-03 10:20 | PM | Reviewed, kept `tracked` | "New evidence reinforces the existing decision, no scope change" |

Every field the brief's audit-trail deliverable asks for falls out of this table directly: who or
what initiated each change, when, and the documented rationale — queryable, not a screenshot of a
decision.
