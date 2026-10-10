# PM overview

> Status: `draft` · Last updated: 2026-10-10

The architecture specifies how a PM drives one run
([`02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md#ui-shape)).
It does not yet specify where a PM looks to answer the questions asked in every program review:
*What do we have? How sure are we? What needs me? What changed?* This doc does. Almost all of it is
`new`; it adds views over data the architecture already stores, and needs no new entities.

## The four questions

| Question | View | Requirements |
|---|---|---|
| What do we have? | Portfolio | `FR-OV-01` … `FR-OV-05` |
| How sure are we? | Evidence coverage | `FR-OV-06` … `FR-OV-09` |
| What needs me? | Inbox | `FR-OV-10` … `FR-OV-12` |
| What changed? | Change feed and reporting | `FR-OV-13` … `FR-OV-16` |

## Portfolio — what do we have?

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-OV-01 | Show all requirements of a vehicle line in one list with: title, domain, markets, status, tier, score, confidence, evidence level, number of sources, last change. | M | new |
| FR-OV-02 | Filter and sort that list by every column, and by input family ("show requirements resting on social media only"). | M | new |
| FR-OV-03 | Show summary counts above the list: requirements per status, per tier and per domain, for the current filter. | M | new |
| FR-OV-04 | Show each requirement on a single page: description, metric, acceptance criteria, score breakdown, linked findings with citations, assumptions, history. | M | [06](../architecture/06-prioritization.md), [07](../architecture/07-audit-trail.md) |
| FR-OV-05 | Compare markets side by side: for each requirement, its score and fit per market, so "fits EU, does not fit China" is visible without opening it. | S | [08](../architecture/08-scaling-and-config.md#markets-compose-they-dont-collapse) |

**FR-OV-01** — a PM who has never seen the run that produced a requirement can tell from this row
alone whether it is decided, how important it is, and how well supported.

## Evidence coverage — how sure are we?

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-OV-06 | Show a matrix of domain × input family (feedback, sales, competitor, trend, website, social media) with the number of findings in each cell, so blind spots are visible. | S | new |
| FR-OV-07 | List all sources in scope with type, channel, trust tier, date, findings produced and ingest status. | M | new |
| FR-OV-08 | Mark requirements whose evidence is thin: a single source, a single input family, low trust tier only, or older than a configurable age. | M | new |
| FR-OV-09 | Show the out-of-scope bin and any coverage gap left by a skipped or rejected agent step. | M | [08](../architecture/08-scaling-and-config.md#regulatory-guardrail), [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-four-actions-same-verbs-as-everywhere-else) |

## Inbox — what needs me?

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-OV-10 | Show one list of everything waiting for a PM action: plans awaiting confirmation or steps awaiting review, requirements in review, requirements re-opened by new or contradicting evidence, findings with unassigned market or vehicle line, column mappings to confirm. | M | new |
| FR-OV-11 | Let the PM act on an inbox item directly or jump to it in one click. | S | new |
| FR-OV-12 | Show the state of every run — which steps are done, which is next — without opening the run. | S | [02](../architecture/02-orchestration-and-human-in-the-loop.md#ui-shape) |

## Change feed and reporting — what changed?

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-OV-13 | Show what changed since a chosen date: new requirements, status and tier changes, new evidence on tracked requirements. | S | [07](../architecture/07-audit-trail.md) |
| FR-OV-14 | Generate a dossier per requirement and a board pack for a selected set of requirements. | M | [05](../architecture/05-requirement-lifecycle.md#committee--board-mode) |
| FR-OV-15 | Export the filtered portfolio list as a spreadsheet, including citations. | S | new |
| FR-OV-16 | Answer a PM's question about the portfolio in plain language ("which must-haves for the US rest on fewer than two sources?"), with links to the requirements named in the answer. | C | new |

**FR-OV-14** — the dossier is compiled from the step summaries the PM already accepted, not written
from scratch, so it never says something the PM has not seen.

## Out of this doc

How the PM runs and approves agents is in
[`05-pm-control-and-traceability.md`](05-pm-control-and-traceability.md). Visual design, layout and
navigation are not specified here.
