# Functional requirements

> Status: `draft` · Last updated: 2026-10-10

What the Requirement Evidence Engine must *do*, stated so it can be built against and checked off.
The [architecture docs](../architecture/) say how the system is shaped; these say what a product
manager can expect from it.

Two things here go beyond what the architecture currently describes, and are marked `new` in the
Origin column wherever they appear:

- **A PM overview** — the architecture defines a per-run stepper, but no place where a PM sees the
  whole requirement portfolio at once. See [`04-pm-overview.md`](04-pm-overview.md).
- **Flexible inputs** — the architecture is written around the provided PDF/Excel files plus agent-
  driven web search. Feedback in any shape, PM-supplied websites, and social media are specified in
  [`01-inputs-and-ingestion.md`](01-inputs-and-ingestion.md).

## Map

| Doc | Area | IDs | Count |
|---|---|---|---|
| [`01-inputs-and-ingestion.md`](01-inputs-and-ingestion.md) | Getting feedback, websites and social media in as cited findings | `FR-IN` | 24 |
| [`02-analysis-and-structuring.md`](02-analysis-and-structuring.md) | Situation analysis, competitor benchmarking, clustering | `FR-AN` | 14 |
| [`03-requirements-and-prioritization.md`](03-requirements-and-prioritization.md) | Drafting requirements and scoring them | `FR-RQ`, `FR-PR` | 15 |
| [`04-pm-overview.md`](04-pm-overview.md) | The portfolio view for product management | `FR-OV` | 16 |
| [`05-pm-control-and-traceability.md`](05-pm-control-and-traceability.md) | Step-by-step approval, citations, audit trail | `FR-HL`, `FR-TR` | 17 |
| [`06-lifecycle-and-configuration.md`](06-lifecycle-and-configuration.md) | Two-year tracking loop, scope and configuration | `FR-LC`, `FR-CF` | 13 |

## How to read a requirement

| Column | Meaning |
|---|---|
| **ID** | Stable. Never renumber; retire an ID by striking it through and noting what replaced it. |
| **Requirement** | One testable behaviour, phrased as "The system shall …" (shortened to the verb). |
| **Prio** | `M` must — required for the target end-to-end workflow; priority does not imply it is already implemented. `S` should — expected in a credible product, built if time allows. `C` could — worth stating, not planned for the demo. |
| **Origin** | The architecture doc it is derived from, or `new` if the architecture does not cover it yet. |

Acceptance notes are given below a table only where the requirement alone leaves room for argument.

## The system in one paragraph, for product management

A PM picks a vehicle line and a market, and feeds in whatever evidence exists — BMW's own feedback
and sales files, pasted customer comments, website links, social media exports. The system turns
all of it into individually cited findings, groups them into themes, drafts requirements with a
metric and acceptance criteria, and ranks them with a score the PM can take apart. The PM confirms the plan,
then reviews each agent step; acceptance starts the next agent automatically, and afterwards sees every
requirement — its status, its
priority, how good its evidence is, and what changed since last time — in one overview.

## What the PM gets, by goal

| PM goal | Covered by |
|---|---|
| "Use every piece of evidence we have, wherever it comes from" | `FR-IN-01` … `FR-IN-24` |
| "Know what customers and rivals are telling us" | `FR-AN-01` … `FR-AN-14` |
| "Get requirements I can hand to engineering" | `FR-RQ-01` … `FR-RQ-08` |
| "Understand and defend the ranking" | `FR-PR-01` … `FR-PR-07` |
| "See the state of the whole program at a glance" | `FR-OV-01` … `FR-OV-16` |
| "Stay in control of what the AI does" | `FR-HL-01` … `FR-HL-09` |
| "Prove where a requirement came from" | `FR-TR-01` … `FR-TR-08` |
| "Keep requirements current over two years" | `FR-LC-01` … `FR-LC-07` |
| "Reuse this for another vehicle or market" | `FR-CF-01` … `FR-CF-06` |

## Implementation status (reviewed 2026-10-10)

These requirements describe the target product, not a completion checklist. Current boundaries:

| Area | Implemented | Remaining |
|---|---|---|
| Inputs | Provided PDFs/Excel ingestion with citations; source channel/language/origin metadata; model-cited web summaries | PM-supplied URLs/social uploads, mapping confirmation, complete page snapshots, personal-data handling |
| Analysis | All roster modules, deterministic availability proxy and Critic provenance checks | Separate competitor-scoping gates, live semantic verification, structured cluster editing |
| PM control | Authenticated planning, plan edits before start, sequential live execution, reason-required acceptance/retry/rejection, summary edits, gap-or-abort decision | Mid-run plan adaptation and durable recovery |
| Requirements and scoring | Cited draft/score output stored as step JSON; persisted backlog/latest-score reads and audited status reviews | Automatically publishing accepted outputs into backlog tables, versioning and scheduled lifecycle |
| Overview and reports | Authenticated database portfolio, evidence counts, sales/catalog/study data, accepted research and requirement-level audit history | Successor targets, historical product metrics and board pack |
| Lifecycle | Delta/Tracking module | Recurring refresh, weekly reports, automatic evidence-delta scheduling |

See [decision 0023](../decisions/0023-database-backed-workspace.md) and the
[repository guide](../architecture/12-repo-structure.md). Every build requires a same-origin `/api`; static files have no fixture fallback.

## Not functional requirements

Performance, availability, security hardening, cost per run and model choice are deliberately left
out. They belong in a separate non-functional list once the demo slice runs end to end.
