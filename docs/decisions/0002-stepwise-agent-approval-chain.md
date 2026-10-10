# 0002 — Gate every agent step, not just the drafted requirement and its score

> Date: 2026-10-10 · Status: accepted, partly superseded by [0005](0005-chat-entry-and-orchestrator-planned-steps.md) (the manual "Run" click per agent was removed; accepting a step now starts the next)

## Context

The first pass at this architecture gated the PM in at two points: after a requirement was
drafted, and after it was scored. Everything upstream of drafting — four-plus research agents
reading feedback, option data, sales data, and the web — ran fully unattended and handed the PM a
single combined result to review at the end.

That's cheap to build but expensive to use: if the PM disagrees with one finding from the
Competitor Agent, there's no way to fix just that without re-running (or manually untangling) the
whole batch. It also means a PM can't steer research mid-flight ("focus on EU hot-climate
feedback") — only after the fact.

## Decision

Model a run as an ordered/partially-ordered sequence of `Step`s, one per agent invocation. A step
only starts when the PM explicitly clicks "Run" on it (not automatically, even once its
dependencies are satisfied), and its output — always rendered as a short human-readable summary,
never just raw structured data — only unlocks the next step once the PM clicks **Accept**. **Edit**,
**Retry** (with a steering note), and **Reject** are available at every step, not just at the end.

See [`../architecture/02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md).

## Consequences

- More PM clicks per run than a single end-of-pipeline review. Deliberate — the brief explicitly
  asks for the PM to be "firmly in control of every decision," not just the final one.
- Steering ("retry, but exclude X") becomes cheap and targeted instead of "reject everything, try
  again."
- The audit trail gains one entry per step action, not just one per finished requirement — more
  log volume, but it's what makes a run fully reconstructable after the fact (see
  [`../architecture/07-audit-trail.md`](../architecture/07-audit-trail.md)).
- Requires the orchestrator (LangGraph) to expose an `interrupt()` at every step boundary, not just
  two — informed the tech-stack choice, see
  [`../architecture/09-tech-stack.md`](../architecture/09-tech-stack.md).
