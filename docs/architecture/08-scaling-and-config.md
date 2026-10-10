# Scaling & configuration

> Status: `draft` · Last updated: 2026-10-10 (database workspace; [decision 0023](../decisions/0023-database-backed-workspace.md))

Runs are not limited to G60 or Europe, although supported vehicle-line/market codes are currently mirrored in
backend evidence API types and planner catalog. Workspace selector labels and values are read from active
database ontology rows; the workspace API validates scope against those rows. Every `PipelineRun` (one per chat request) takes a config:
`{vehicle_line, market}` from the PM's message; omitted values become `ALL`. A generation baseline is used by
the Baseline agent, not a separate run column. Swapping to the 1 Series in China is a config
change, not a rewrite.

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
(planned; no persisted per-market sub-score API yet) rather than forcing one global priority — this is the
direct answer to the PM pain point raised
about balancing requirements across regions with different climate, usage, and culture.

## Regulatory guardrail

Findings that read as safety/emissions/type-approval or pricing/business-case in nature are
auto-tagged by the Clustering/Ontology Agent and routed to a visibly separate "flagged, out of
scope" bin — never drafted into a customer requirement. Keeps the demo honestly inside the brief's
boundary instead of silently drifting into engineering or regulatory territory.
