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
| **Prio** | `M` must — the demo slice (G60 × Europe) does not work without it. `S` should — expected in a credible product, built if time allows. `C` could — worth stating, not planned for the demo. |
| **Origin** | The architecture doc it is derived from, or `new` if the architecture does not cover it yet. |

Acceptance notes are given below a table only where the requirement alone leaves room for argument.

## The system in one paragraph, for product management

A PM picks a vehicle line and a market, and feeds in whatever evidence exists — BMW's own feedback
and sales files, pasted customer comments, website links, social media exports. The system turns
all of it into individually cited findings, groups them into themes, drafts requirements with a
metric and acceptance criteria, and ranks them with a score the PM can take apart. The PM starts
and approves each agent step by hand, and afterwards sees every requirement — its status, its
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

## Architecture gaps these requirements open

Adopting the `new` requirements means changing the architecture docs. Nothing below is done yet;
each needs an edit to the named doc and, where it reverses a choice, an entry in
[`../decisions/`](../decisions/).

| Gap | Affects | Triggered by |
|---|---|---|
| `Source.type` only knows `internal_pdf \| internal_xlsx \| web`; no notion of channel, platform, language or upload | [`04-data-model.md`](../architecture/04-data-model.md#source) | `FR-IN-02`, `FR-IN-12` |
| Web content is cited by URL + retrieval date only; no stored snapshot, so a deleted post leaves a dead citation | [`03-ingestion.md`](../architecture/03-ingestion.md) | `FR-IN-15` |
| No personal-data handling for social media and free-text feedback | [`03-ingestion.md`](../architecture/03-ingestion.md) | `FR-IN-17` |
| Web sources are found only by agent search; a PM cannot hand over a specific URL or site | [`01-agents.md`](../architecture/01-agents.md) | `FR-IN-06`, `FR-IN-07` |
| `sample_size` has no counterpart for social reach (likes, replies), which is not a sample | [`04-data-model.md`](../architecture/04-data-model.md#finding) | `FR-IN-13` |
| UI is specified as a per-run stepper only; no portfolio, inbox or coverage view | [`02-orchestration-and-human-in-the-loop.md`](../architecture/02-orchestration-and-human-in-the-loop.md#ui-shape) | `FR-OV-*` |
| `Finding.signal_type` omits `strategic_continuity` and `business_signal`, which [`01-agents.md`](../architecture/01-agents.md) has agents produce | [`04-data-model.md`](../architecture/04-data-model.md#finding) | `FR-AN-01`, `FR-AN-03` |

## Not functional requirements

Performance, availability, security hardening, cost per run and model choice are deliberately left
out. They belong in a separate non-functional list once the demo slice runs end to end.
