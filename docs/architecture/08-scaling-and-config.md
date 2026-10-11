# Scaling & configuration

> Status: `draft` · Last updated: 2026-10-11 (complementary comparison evidence and extraction)

Nothing about G60 or "Europe" is hardcoded. Every `PipelineRun` (one per chat request) takes a config:
`{vehicle_line, market, generation_baseline}`, read from the PM's message or asked back by the
orchestrator if missing. Swapping to the 1 Series in China is a config
change, not a rewrite.

## Comparison research configuration

`COMPARISON_SEARCH_MODEL` selects the model used by the protected Models comparison API for
source discovery. It falls back to an explicitly configured `RESEARCH_AGENT_MODEL`, then `gpt-4.1`.
The general research agents retain their existing defaults. Comparison searches request high
search context and actual result-source URLs. `COMPARISON_EXTRACTION_MODEL` defaults to `gpt-4.1`
and must support strict structured outputs for original source-line selection. Neither setting
changes embeddings or the database schema. See [decision 0031](../decisions/0031-recoverable-competitor-collection.md)
and [decision 0033](../decisions/0033-complementary-competitor-evidence.md). Collection uses up to
two missing-field searches and six source pages per target within a shared 250-second deadline.

## Domain taxonomy is config, not code

Exterior / Interior / Powertrain / Driver Assistance / Infotainment / Comfort & Space / Usability
/ Variant & Package / Range & Charging / Safety (flagged out of scope) — stored as an editable `Ontology` store (see
[`04-data-model.md`](04-data-model.md#ontology)), not a hardcoded enum, so a future BEV-only line
can extend it without a code change.

## New source = one adapter

Every ingestion agent implements the same `Source → Finding[]` interface (see
[`03-ingestion.md`](03-ingestion.md)). A new feedback export, a new web source, a new internal
system plugs in without touching clustering, drafting, or scoring.

## Markets compose, they don't collapse

A requirement can carry per-market sub-scores and a market-fit flag ("fits EU, doesn't fit China")
rather than forcing one global priority — this is the direct answer to the PM pain point raised
about balancing requirements across regions with different climate, usage, and culture.

## Regulatory guardrail

Findings that read as safety/emissions/type-approval or pricing/business-case in nature are
auto-tagged by the Clustering/Ontology Agent and routed to a visibly separate "flagged, out of
scope" bin — never drafted into a customer requirement. Keeps the demo honestly inside the brief's
boundary instead of silently drifting into engineering or regulatory territory.
