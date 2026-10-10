# 0008 — Normalize all evidence to one vocabulary; one retrieval interface that returns citations

> Date: 2026-10-11 · Status: accepted

## Context

Ingestion left five raw evidence tables (feedback comments, PDF text chunks, equipment options,
customer-study cells, sales volumes) that each used their own labels: `derivate` vs. model names vs.
sheet names, country codes vs. "Europe", `BEVE` vs. variant names. The `finding` table was empty and
had no way to cite more than one source row. Agents would have had to write their own SQL and could
cite anything.

## Decision

1. **Add the same filter fields to every evidence table:** `vehicle_line` (F70, G60, G68, G70),
   `market_code` (EU, CN, US, RoW), ontology `domain_id`, `polarity`, `powertrain`. Reference data lives
   in tables (`country_market`, `model_variant`), not in code.
2. **`finding_evidence`** links a finding to the raw rows behind it, one foreign key per row across five
   kinds, with a check that exactly one is set. The `evidence_item` view is the single definition of
   what can be cited.
3. **Agents read through `knowledge/tools.py`:** hybrid vector + keyword search (rank fusion in SQL),
   exact lookups for options, sales and studies, exact counts, and `cite()`. Every result carries a
   `Citation` (file, locator, verbatim quote). Counts come from SQL, never from sampled text.
4. **Domain filters match the domain and all its child categories.**

## Assumptions recorded (confirm with BMW)

GB and Norway count as Europe; `BEVE` means battery-electric (only appears for G60/G70, never F70);
the `G60_G68` sales sheet's China row is G68, the others G60; catalog variant powertrain is read from
the model names.

## Consequences

- One question can span feedback, catalog, sales and studies with the same line/market filters.
- **There is no customer feedback for China** (the feedback files cover EU 3,292, US 8,783, RoW 1,696).
  China evidence is limited to the customer study and sales data; agents must say so rather than imply
  coverage.
- 2,666 comments have no domain (2,082 unclassified in the source, 400 blank, 184 with non-product labels).
- The backfill touched all 13.7k feedback rows with an HNSW index in one migration, which took ~4 minutes
  and timed out the migration client; the server completed it. Rebuild the index before future bulk updates.
- Still open: deriving `finding` rows, requirement versioning ("versioned sets"), web ingestion into
  the same tables.

See [`../architecture/11-knowledge-layer.md`](../architecture/11-knowledge-layer.md).
