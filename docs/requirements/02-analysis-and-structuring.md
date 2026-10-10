# Analysis & structuring

> Status: `draft` · Last updated: 2026-10-10

Stages 01 (situation analysis) and 02 (structure & context) of the pipeline: from raw findings to
deduplicated themes. Derived from [`01-agents.md`](../architecture/01-agents.md),
[`10-competitor-benchmarking.md`](../architecture/10-competitor-benchmarking.md) and
[`08-scaling-and-config.md`](../architecture/08-scaling-and-config.md).

## Situation analysis

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-AN-01 | Derive a baseline from the previous generation — what customers valued and criticised, how sales developed — as findings marked as strategic continuity. | S | [01](../architecture/01-agents.md#roster) |
| FR-AN-02 | Extract complaints, unmet needs and praise from customer feedback, each with its market and, where the source provides one, its sample size. | M | [01](../architecture/01-agents.md#roster) |
| FR-AN-03 | Compute option uptake per market from sales volumes and the option list, as a revealed-preference signal alongside what customers say. | M | [01](../architecture/01-agents.md#roster) |
| FR-AN-04 | Identify market and technology trends from web research, and label every such finding as an assumption about the future rather than an observed fact. | S | [01](../architecture/01-agents.md#roster), [ADR 0003](../decisions/0003-critic-agent-and-agent-split.md) |
| FR-AN-05 | Classify every finding by signal type and sentiment. | M | [04](../architecture/04-data-model.md#finding) |

## Competitor benchmarking

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-AN-06 | Let the PM fix an anchor vehicle (line and variant) and propose a segment — price, body style, seats, powertrain, range, size — that the PM can override band by band before any search runs. | S | [10](../architecture/10-competitor-benchmarking.md#2--segment-definition-what-the-same-bracket-means) |
| FR-AN-07 | List the rival models inside the segment per market, ranked by similarity, and let the PM choose which to carry forward. | S | [10](../architecture/10-competitor-benchmarking.md#4--shortlist-pick-the-comparison-vehicles) |
| FR-AN-08 | Compare anchor and rivals per aspect and per source type — owner voice with owner voice, test with test, spec with spec — in relative terms, and report "insufficient data" where either side is thin. | S | [10](../architecture/10-competitor-benchmarking.md#6--relative-comparison-against-the-anchor) |
| FR-AN-09 | Compare specifications only where both sides use the same measurement standard. | S | [10](../architecture/10-competitor-benchmarking.md#6--relative-comparison-against-the-anchor) |
| FR-AN-10 | Turn clear deltas into findings: a competitor advantage where the rival leads, a strength to defend where BMW leads. | M | [10](../architecture/10-competitor-benchmarking.md#6--relative-comparison-against-the-anchor) |

For the demo, `FR-AN-10` is satisfied with a hand-confirmed rival set; `FR-AN-06` to `FR-AN-09`
describe the full path and remain a proposal until the architecture adopts it.

## Structure & context

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-AN-11 | Group findings that describe the same customer issue into one cluster, across sources and input families, and show which findings each cluster contains. | M | [01](../architecture/01-agents.md#roster) |
| FR-AN-12 | Map every cluster onto the domain taxonomy (Exterior, Interior, Powertrain, Driver Assistance, Infotainment, Comfort & Space, Usability, Variant & Package). | M | [08](../architecture/08-scaling-and-config.md#domain-taxonomy-is-config-not-code) |
| FR-AN-13 | Let the PM merge, split and relabel clusters and move a finding between clusters. | M | [02](../architecture/02-orchestration-and-human-in-the-loop.md#the-four-actions-same-verbs-as-everywhere-else) |
| FR-AN-14 | Detect findings that are regulatory, engineering-internal or pricing in nature and route them to a visible out-of-scope bin instead of into a cluster. | M | [08](../architecture/08-scaling-and-config.md#regulatory-guardrail) |

**FR-AN-11** — a cluster reports how many independent sources and how many input families it draws
on. Twenty forum posts quoting one article count as one independent source.
