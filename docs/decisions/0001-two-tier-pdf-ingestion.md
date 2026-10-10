# 0001 — Two-tier PDF ingestion instead of naive text extraction

> Date: 2026-10-10 · Status: accepted

## Context

The provided PDFs (`*_OptionList.PDF`) are structured option/equipment listings. The brief asks
for findings and requirements that are traceable to their sources. A naive "dump the PDF to text,
chunk by token count, embed" pipeline would destroy the table structure and produce citations like
"chunk 47" instead of a page/row a PM could actually go look at.

## Decision

Parse every PDF (and, by extension, every source) on two tracks:

1. **Deterministic** — layout-aware table extraction into typed rows, no model in the loop. Feeds
   structured stores (e.g. an `Options` table) directly.
2. **Semantic** — heading-aware chunking + embedding for narrative text, locator kept per chunk.

Both converge on a `Finding` with a locator and an `evidence_level` set by *how* it was extracted
(`Verified` for deterministic, `Interpreted` for semantic — further gradable by the Critic Agent
or a PM override).

## Consequences

- More ingestion code than a single embed-everything pipeline.
- Every citation in the UI can point at an exact row or page, not an approximate chunk.
- `evidence_level` becomes a meaningful, inspectable field instead of a constant.

See [`../architecture/03-ingestion.md`](../architecture/03-ingestion.md).
