# Lifecycle & configuration

> Status: `draft` · Last updated: 2026-10-10

What happens to a requirement over the roughly two-year program, and what keeps the system from
being a one-off for G60 in Europe. Derived from
[`05-requirement-lifecycle.md`](../architecture/05-requirement-lifecycle.md),
[`00-overview.md`](../architecture/00-overview.md#scope) and
[`08-scaling-and-config.md`](../architecture/08-scaling-and-config.md).

## Requirement lifecycle

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-LC-01 | Carry every requirement through the statuses draft, in review, tracked, rejected, challenged, superseded. | M | [05](../architecture/05-requirement-lifecycle.md) |
| FR-LC-02 | Let the PM approve, reject, edit or challenge a requirement individually, independent of the run that produced it. | M | [05](../architecture/05-requirement-lifecycle.md), [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-full-chain) |
| FR-LC-03 | On a challenge, have the agents research again with the PM's objection as input, and return the requirement as a draft. | S | [05](../architecture/05-requirement-lifecycle.md) |
| FR-LC-04 | Re-check tracked requirements against newly ingested evidence on a schedule and whenever a new source is added. | S | [05](../architecture/05-requirement-lifecycle.md) |
| FR-LC-05 | Re-open a tracked requirement for review only when evidence is new, contradicting or stale; stay silent when nothing material changed. | S | [05](../architecture/05-requirement-lifecycle.md) |
| FR-LC-06 | Let the PM supersede a requirement with another and keep the link between the two. | C | [05](../architecture/05-requirement-lifecycle.md) |
| FR-LC-07 | Make accepted requirements and dossiers available as context for later runs. | S | [00](../architecture/00-overview.md#the-five-stages) |

**FR-LC-04** — "whenever a new source is added" is what connects the flexible inputs to the
tracking loop: a PM pasting in a fresh dealer report or adding a new forum thread sees which
tracked requirements it touches, without starting a full run.

## Scope & configuration

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-CF-01 | Run for any configured vehicle line and market; nothing is specific to one line or market. | M | [08](../architecture/08-scaling-and-config.md) |
| FR-CF-02 | Let the domain taxonomy and the lists of vehicle lines and markets be edited without a code change. | S | [08](../architecture/08-scaling-and-config.md#domain-taxonomy-is-config-not-code) |
| FR-CF-03 | Hold per-market scores and a market-fit flag on a requirement instead of forcing one global priority. | S | [08](../architecture/08-scaling-and-config.md#markets-compose-they-dont-collapse) |
| FR-CF-04 | Restrict drafted requirements to customer-facing topics; regulatory, engineering-internal and pricing topics are never drafted. | M | [00](../architecture/00-overview.md#scope) |
| FR-CF-05 | Use cost or effort only as a coarse, PM-editable prioritization factor. | M | [00](../architecture/00-overview.md#scope), [06](../architecture/06-prioritization.md) |
| FR-CF-06 | Let weights, tier thresholds, trust tiers, staleness age and enabled input connectors be set per program. | S | [06](../architecture/06-prioritization.md), `FR-IN-19`, `FR-IN-23`, `FR-OV-08` |
