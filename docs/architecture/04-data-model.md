# Data model

> Status: `draft` · Last updated: 2026-10-10

Everything is traceable because everything points backward. A PM looking at a requirement can walk
back to the exact cell or paragraph that produced it; a PM looking at the audit log can tell who or
what changed what, and why.

```mermaid
erDiagram
    SOURCE ||--o{ FINDING : "produces, with a locator"
    FINDING }o--o{ CLUSTER : "deduped & grouped into"
    ONTOLOGY ||--o{ CLUSTER : "tags the domain of"
    CLUSTER ||--o| REQUIREMENT : "drafted into"
    REQUIREMENT ||--o{ SCORE : "scored, versioned"
    PIPELINERUN ||--o{ STEP : "made of"
    STEP ||--o{ FINDING : "a step's output"
    STEP ||--o| CLUSTER : "a step's output"
    STEP ||--o| REQUIREMENT : "a step's output"
    STEP ||--o| SCORE : "a step's output"
    AUDITEVENT }o--|| FINDING : "logs changes to"
    AUDITEVENT }o--|| CLUSTER : "logs changes to"
    AUDITEVENT }o--|| REQUIREMENT : "logs changes to"
    AUDITEVENT }o--|| SCORE : "logs changes to"
    AUDITEVENT }o--|| STEP : "logs changes to"
```

## Source

`id, type (internal_pdf | internal_xlsx | web), uri, vehicle_line, market, retrieved_at`

## Finding

`id, source_id, locator (page/row/cell or url+retrieved_at), text, signal_type (complaint |
unmet_need | competitor_advantage | market_trend | praise), evidence_level (Verified | Interpreted
| source-trust tier), sentiment, sample_size, market, extracted_by, created_at`

See [`03-ingestion.md`](03-ingestion.md) for how `locator` and `evidence_level` get set.

## Cluster

`id, label, ontology_domain_id, member_finding_ids[], created_at`

## Ontology

`id, kind (domain | market | vehicle_line), key, label, parent_id (nullable), active`

A first-class, editable store rather than a hardcoded enum — see
[`08-scaling-and-config.md`](08-scaling-and-config.md). This is what makes the domain taxonomy
(Exterior/Interior/Powertrain/…) and the vehicle-line/market lists config, not code.

## Requirement

`id, title, description, ontology_domain_id, markets[], vehicle_line, metric,
acceptance_criteria, evidence_level, assumptions[], uncertainties[], status (draft | pm_review |
tracked | rejected | challenged | superseded | proposed), linked_finding_ids[],
linked_cluster_ids[], origin (scheduled_pipeline | pm_query), created_by_run_id`

`status` transitions are defined in [`05-requirement-lifecycle.md`](05-requirement-lifecycle.md).

## Score

`id, requirement_id, customer_relevance, business_signal, strategic_fit, effort_proxy, confidence,
composite, weight_vector_version, rationale, computed_by, computed_at`

Versioned — a new `Score` row per re-scoring, never an overwrite. See
[`06-prioritization.md`](06-prioritization.md).

## AuditEvent

`id, entity_type, entity_id, actor (agent name | pm user), action, before, after, rationale,
timestamp`

Append-only. See [`07-audit-trail.md`](07-audit-trail.md).

## PipelineRun & Step

Introduced in [`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md).

**PipelineRun:** `id, trigger (scheduled | pm_query), vehicle_line, market, query_text (nullable),
status (in_progress | completed | aborted), created_by, created_at`

**Step:** `id, run_id, agent_name, stage, depends_on_step_ids[], status (queued | awaiting_launch |
running | awaiting_review | accepted | rejected), human_readable_summary, structured_output_refs[],
launched_by, launched_at, resolved_by, resolved_at, pm_note`

Every launch, accept, edit, retry, and reject on a `Step` is also an `AuditEvent` — the run itself
is fully reconstructable from the audit log alone.
