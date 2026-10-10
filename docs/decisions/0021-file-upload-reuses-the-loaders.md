# 0021 — Files are uploaded from the Sources view and stored by the existing loaders

> Date: 2026-10-10 · Status: accepted · Builds on [0006](0006-raw-tables-and-cited-pdf-chunks.md), [0007](0007-option-availability-and-ontology-seed.md), [0008](0008-knowledge-layer-normalization-and-retrieval.md), [0016](0016-backend-owned-authentication.md)

## Context

The evidence store only held the files BMW provided, loaded once by scripts run from a shell. A PM could not add a
file. The loaders also only wrote the raw columns: the normalized ones (vehicle line, market, domain, polarity,
powertrain, model variant) were backfilled once by the knowledge-layer migration, so a file loaded after it was
invisible to every filter, and loading options failed on the `variant_id` the migration made mandatory.

## Decision

1. **`POST /api/sources`** (protected) takes one file as the raw request body, with `filename`, an optional `line`
   and `replace` in the query. No multipart parser is added. The limit is 25 MB.
2. **The same loaders store it.** `app/ingest/load_excel.py`, `load_pdfs.py` and `load_options.py` now expose one
   function per file; the scripts and the upload (`app/ingest/upload.py`) both call them. There is one ingestion path.
3. **A spreadsheet is recognised by its layout**, not its name: study sheets by their names (`CN_EU…`, `US_…`),
   sales by a market code and a number in the first rows, feedback by the 12-column export. Anything else is refused
   with a message that names the supported layouts. Column mapping for unknown layouts (`FR-IN-09`) is not built.
4. **A PDF is always stored as cited text passages.** Its equipment tables are also stored when the catalog layout is
   found and a vehicle line was given.
5. **The loaders normalize what they load**, with the migration's rules applied to the rows of the one file, and
   register model variants. Nothing depends on a one-time backfill any more.
6. **The file name is the source's identity.** A name that is already loaded is refused (409) unless `replace` is
   set; the UI asks for that explicitly. A file whose rows findings already cite cannot be replaced.
7. **The request answers when the file is stored.** Embeddings are computed before the write transaction, and the
   write is one transaction per file, so a failure leaves nothing behind. There is no job table.

## Consequences

A large feedback export keeps the request open for a minute or two; a hosted backend needs a proxy timeout above
that, or a background job later. Who uploaded a file is not recorded: `source` has no column for it in the project
database (`20261010_web_research_agent.sql` is not applied there). Sales sheets must be named after their vehicle
line, as in the provided file. Word documents, pasted text and CSV are not accepted yet.
