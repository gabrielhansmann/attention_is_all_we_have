# Requirements & prioritization

> Status: `draft` · Last updated: 2026-10-10

Stages 03 (requirements definition) and 04 (prioritization). Derived from
[`04-data-model.md`](../architecture/04-data-model.md#requirement) and
[`06-prioritization.md`](../architecture/06-prioritization.md).

## Requirements definition

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-RQ-01 | Draft a requirement from a cluster: title, description from the customer's point of view, domain, markets, vehicle line. | M | [01](../architecture/01-agents.md#roster) |
| FR-RQ-02 | Give every requirement a measurable metric and acceptance criteria; where no defensible number exists, say so explicitly instead of inventing one. | M | [04](../architecture/04-data-model.md#requirement) |
| FR-RQ-03 | Link every requirement to the findings and clusters it rests on. | M | [04](../architecture/04-data-model.md#requirement) |
| FR-RQ-04 | List the assumptions and uncertainties behind each requirement separately from its evidence. | M | [04](../architecture/04-data-model.md#requirement) |
| FR-RQ-05 | Show an overall evidence level per requirement, derived from its linked findings. | M | [04](../architecture/04-data-model.md#requirement) |
| FR-RQ-06 | Let the PM edit any field of a requirement; every edit is recorded with its reason. | M | [07](../architecture/07-audit-trail.md) |
| FR-RQ-07 | Flag requirements that overlap with or contradict an existing one before the PM approves a duplicate. | S | new |
| FR-RQ-08 | Let the PM create a requirement by hand and attach existing findings to it, marked as PM-originated. | C | new |

## Prioritization

| ID | Requirement | Prio | Origin |
|---|---|---|---|
| FR-PR-01 | Score every requirement as a composite of customer relevance, business signal, strategic fit and effort, and show each component's value and weight. | M | [06](../architecture/06-prioritization.md) |
| FR-PR-02 | Base customer relevance on prevalence relative to sample size, sentiment severity and the number of independent corroborating sources — not on raw mention counts or social reach. | M | [06](../architecture/06-prioritization.md), `FR-IN-13` |
| FR-PR-03 | Show confidence as its own indicator, separate from the rank. | M | [06](../architecture/06-prioritization.md) |
| FR-PR-04 | Assign a tier — must-have, should-have, watch-list — from the composite score. | M | [06](../architecture/06-prioritization.md#worked-example) |
| FR-PR-05 | Let the PM change the weights per program and override any single component, then re-score. | M | [06](../architecture/06-prioritization.md) |
| FR-PR-06 | Keep every earlier score with the weights it used; re-scoring adds a version, it never overwrites. | M | [04](../architecture/04-data-model.md#score) |
| FR-PR-07 | Generate a one-sentence rationale per score that names the evidence driving it. | M | [06](../architecture/06-prioritization.md) |

**FR-PR-03** — "high potential, thin evidence" and "confidently low priority" must look different
in every list and export, not only on the detail page.

**FR-PR-04** — tier thresholds (currently ≥ 0.65 / 0.40–0.65 / < 0.40) are configuration. A PM
override of a tier is allowed, is recorded with a reason, and stays visibly marked as an override.
