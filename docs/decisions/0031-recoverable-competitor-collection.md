# 0031: Recoverable competitor collection and bounded model overview queries

Date: 2026-10-11
Status: accepted

## Context

Competitor cohorts can contain no measurements when discovery returns a marketing page,
configurator or obsolete PDF. Even readable technical PDFs lost facts when the extractor
rewrote quotations. Repeated database queries also made model listing and feedback overviews slow.

## Decision

Refine decision 0025 without changing its protected API, comparison rules or frontend contract.
Prefer technical PDFs and specification pages in actual search results. Follow bounded PDF
links actually present on a page when hosted by the same publisher or its subdomains. Preserve
HTML table-cell boundaries. If source collection yields no numerical findings, reserve capacity
for a fresh search for the exact model, variant and market; accept only URLs returned by its
search tool. The per-rival recrawl control uses this recovery path too. Single-finding recrawls
retain their original source identity, and reevaluation does not pretend to perform a new crawl.
Discovery confirms an unverified variant lead against a dedicated current technical-source search
when the first result only provides a marketing page. `COMPARISON_SEARCH_MODEL` defaults to
`gpt-4.1` with high search context, with an explicit `RESEARCH_AGENT_MODEL` retained as a fallback
override. The existing API key is reused. Extraction remains a separate configurable model and
uses strict structured outputs to keep measurement and identity line selections distinct.

Have extraction select original, one-based source line spans; the server constructs the quote
from those lines. HTML identity must be in the local section or recorded document title. PDF
table identity must be on the same page, except continuation pages may use an actual technical
PDF filename explicitly containing the exact variant. The server resolves that filename identity
even when the extraction step selects a missing or incomplete continuation-page header.
Generic filenames and another page's
header cannot establish variant scope. Canonical units must still be explicit in the value row;
standards, powertrain, measurement basis and period remain required for comparable findings.
Qualitative claims retain the original quotation rather than an unverified generated summary.

Bound provider calls, fetched documents and total collection time. Divide remaining collection
time across targets so an unreachable rival cannot consume every later rival's allowance.
Cache robots policies only within a collection request and apply their path rules to every URL.
Keep public-address, redirect, TLS, robots and immutable-source safeguards. Source or extraction
failure becomes a visible coverage note while previous evidence and timestamps remain available.

Read the model registry, variant inventory and market inventory in batches. Obtain the first
three cited feedback examples per section with a partitioned query instead of a query per section.
Warm registry reads use four queries; a dataset section packet uses five queries regardless of
the number of feedback sections. Identity provenance, counts, citations and ordering remain intact.

## Consequences

- A technical source can still lack explicit units, standards or exact variant context. Those
  gaps remain visible and unconfirmed numbers stay out of the median and mean.
- Manufacturer sources and generated interpretation still need human validation; complete
  competitor coverage is not guaranteed by a successful HTTP request.
- No schema migration, public endpoint, new credential provider or browser database access is needed.
- Query-count regressions and citation/recovery behavior are covered by automated checks.
- Failed live-database test setup reports only the exception class, without retaining the
  credential-bearing connection exception in a traceback chain.
