# 0024 — A PM adds a website as a source; the Sources view gets a graph and tabs

> Date: 2026-10-10 · Status: accepted · Builds on [0006](0006-raw-tables-and-cited-pdf-chunks.md), [0009](0009-web-search-through-the-llm.md), [0020](0020-source-viewer-for-citations.md), [0021](0021-rounded-chat-first-frontend.md), [0023](0023-file-upload-reuses-the-loaders.md)

## Context

The Sources view was one long page: a coverage table, an upload form and a file table. Websites were not sources at
all. The web agents read pages during a run and kept a short snapshot in the step output, which no view showed, and
a PM could not add a page (`FR-IN-06`).

## Decision

1. **`POST /api/sources/web`** (protected) takes a URL with an optional vehicle line, market and trust tier. The
   backend fetches that one page and stores it like a PDF: a `source` row of type `web` whose `uri` is the URL, and
   one `chunk` per passage, embedded. Evidence search and the agents find it through the existing `evidence_item`
   view with no schema change.
2. **A passage is cited as "page N"**, N being its position on the page. The view builds the locator from
   `chunk.page`, so a website reuses the catalog's citation form and its kind is `pdf_text`. The source viewer shows
   the passage with its neighbours and links to the page.
3. **Only public addresses are fetched.** http(s) only, no credentials in the URL, and every address, redirects
   included, must resolve to a public IP before a request is made. The limit is 3 MB and 150 passages. Text comes
   from the served HTML with scripts, navigation, headers, footers and forms left out. No crawling, no JavaScript.
4. **`GET /api/sources/web-research`** lists the websites the Market & Trend and Competitor agents read, from the
   stored step outputs (`findings[].source_url`, `skipped[].source`). Nothing new is written by a run. A PM can
   store such a page with one click, with the run's scope and the agent's trust tier.
5. **`DELETE /api/sources/{id}`** removes a stored website and its passages. It refuses files, and a page that
   findings cite.
6. **`GET /api/sources/graph`** returns the rows each source holds per vehicle line and market. The Sources view
   draws them as a layered graph: sources, vehicle lines, markets. Circle size and line width show rows of evidence.
7. **The Sources view has four tabs**: Graph (default), Files, Websites, Coverage, under a summary row. The upload
   form opens on request.
8. **Graph colours**: files use BMW Blue, websites `#d95926`. The pair was checked with the dataviz palette
   validator on white. Kind is never colour alone: websites an agent read are hollow, and every node is labelled.

## Consequences

- A stored page is a snapshot from the day it was fetched. "Fetch again" replaces it.
- The text of a web page is untrusted input that agents now read. The trust tier labels it; the Critic's rules for
  `forum_social` sources apply. Nothing in the text is treated as an instruction.
- The address check and the request resolve the host separately, so a hostile DNS server could answer differently
  the second time. Acceptable for signed-in PMs on a demo; pin the resolved address before hosting more widely.
- A website appears as kind `pdf_text` in Evidence search. A separate kind needs a change to the `evidence_item`
  view and the retrieval tools.
- Who added a page is not recorded, as for files (the `added_by` column of `20261010_web_research_agent.sql` is not
  in the project database).
- Pages behind a login, a bot check or client-side rendering are refused with a message. Social media (`FR-IN-08`)
  and pasted text (`FR-IN-07`) are still not built.
- The graph draws at most ten agent-read websites; the rest are listed in the Websites tab.
