# 0020 — Citations open a source viewer: the passage in context and the original file

> Date: 2026-10-10 · Status: accepted · Builds on [0008](0008-knowledge-layer-normalization-and-retrieval.md), [0016](0016-backend-owned-authentication.md)

## Context

Every finding carried a citation (file, locator, verbatim quote), but the chat showed only the agents' plain-text
summaries. A reader could not see the quote, the passage around it, or the document it came from.

## Decision

1. **Numbered chips on each claim** (step-card findings, `[finding-id]` markers in the dossier). Hover previews file,
   locator and quote; click opens a side panel. This is the pattern used by Perplexity, ChatGPT and Claude.
2. **The panel shows the cited passage highlighted among its neighbours**: the whole catalog page for a PDF chunk, the
   two comments either side for a customer comment. `GET /api/evidence/{kind}/{id}/context` (in `knowledge/library.py`)
   resolves it from stored rows only.
3. **The original is served by the backend**: `GET /api/sources/{id}/file` returns the provided file from `data/`, inside
   the `protected` router. Only plain file names registered in `source` are served. The frontend fetches it with the
   bearer token and opens the blob at `#page=N`, because a plain link cannot carry the token.
4. **Findings without a row id** (agents that cite only file and locator) get a chip that shows that text; there is
   nothing to look up.

## Consequences

Excel sources open the whole workbook (browsers cannot jump to a row); the neighbouring-rows view covers that. The
original is only available where `data/` is present on the server.
