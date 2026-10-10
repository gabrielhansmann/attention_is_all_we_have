# 0004 — Supabase Postgres + pgvector for storage; OpenAI embeddings

> Date: 2026-10-10 · Status: accepted

## Context

The tech stack named "Postgres + pgvector" without choosing a host or an embedding model. A
Supabase project already exists, and an OpenAI API key is available in `.env`. Claude does not
produce embeddings, so a second provider is needed.

## Decision

1. **Host on Supabase.** One managed Postgres holds relational entities, embeddings (pgvector
   0.8), the LangGraph checkpointer state, and the docs mirror tables. Raw PDFs/Excel stay out of
   git (`data/` is gitignored); Supabase Storage can hold them later.
2. **Embed with OpenAI `text-embedding-3-small`** (1536 dims, cosine distance, HNSW index). Only
   `finding.text` and `chunk.content` are embedded. Option codes and sales volumes stay exact,
   un-embedded data, joined and filtered directly.
3. **Backend-only access for now.** RLS is enabled on every table with no policies; only the
   service role or a direct connection can read/write. The frontend goes through the API.
4. **Append-only audit log enforced in the database** with triggers, not just application code.
5. **Schema is applied via migration files** committed under `supabase/migrations/`.

## Consequences

- The vector dimension is fixed in the column type. Switching model (e.g. `text-embedding-3-large`
  or Voyage) means re-embedding all rows and altering the column.
- LangGraph's Postgres checkpointer needs the direct or session-pooler connection string.
- Browser clients cannot query tables directly until RLS policies are added.
- 11 foreign keys are unindexed by choice (tables empty); revisit once query patterns are known.
- The feedback files' languages are not yet verified; if retrieval quality is poor on the real
  data, revisit the embedding model.

See [`../architecture/09-tech-stack.md`](../architecture/09-tech-stack.md) and
[`../architecture/04-data-model.md`](../architecture/04-data-model.md#as-implemented-supabase-supabasemigrations20261010_init_schemasql).
