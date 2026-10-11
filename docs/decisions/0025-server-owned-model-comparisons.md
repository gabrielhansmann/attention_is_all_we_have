# 0025: Server-owned model overviews and reproducible competitor benchmarks

Date: 2026-10-11
Status: accepted

## Context

Product managers need a compact overview for every model in the dataset, sourced competitor
comparisons, manually added models, and the existing chat with the correct context already loaded.
The default market is Germany/Europe. Comparisons must run in the Supabase-backed backend hosted
on Vercel, not use frontend fixtures or direct browser database access. Web evidence must show its
crawl time and support recrawling and reevaluation. Diagrams must distinguish our model, each
competitor, the median and the mean.

## Decision

Discover model families from dataset identities and variants from `model_variant`. Register manual
models separately. The four current families and twenty variants are data, not an application roster.
The protected `/api/models` API owns collection, persistence, comparison arithmetic and validation.
The frontend renders up to six numerical diagrams, expandable complete findings, a qualitative
source matrix, internal feedback/study diagrams, selected competitors and a scoped research chat.

Store research runs, explicit rival cohorts and immutable source-backed observations. Public web
search proposes search leads and returns candidate addresses. A lead is not a verified finding.
Only addresses actually returned by search tools are eligible for automatic collection. A manually
selected competitor can include an exact variant and an explicit public source URL; it undergoes
the same fetch and extraction checks and is labelled manual. Fetch only
public HTTP(S) addresses, validate redirects, honor robots.txt and document inaccessible sources.
Scrape HTML and bounded technical PDFs; never substitute search summaries for raw quoted values.
Extract public evidence with the existing AI service, then validate the quotation, numeric token,
unit, powertrain and explicit measurement standard. Extract internal catalog tables deterministically
on the backend; internal passages are not sent out for specification extraction. Ambiguous columns
or missing cells yield gaps. This decision does not change the existing user-initiated AI chat.

Benchmarks exclude the reference model and give each selected competitor family one vote. Require
matching market, powertrain, canonical unit, test standard, measurement basis and model period.
Show the competitor median (middle sorted value; average two middle values for even n) and the
arithmetic mean. For specification intervals, aggregate endpoints separately and draw an interval,
never an undocumented midpoint. Display n, contributors and exclusions. Do not pool subjective
study ratings, web reviews, evidence counts and physical specifications. Qualitative features have
no arithmetic mean or median and missing evidence does not prove a feature is absent.

Each rival card exposes crawl and reevaluation controls, even before any fact is extracted. A
cohort-scoped rival ID selects its known source URLs; cross-model IDs are rejected. A recrawl
appends a new source snapshot and exposes both crawl and extraction/evaluation timestamps.
A reevaluation re-reads current Supabase evidence and re-extracts stored public sources without
pretending they were freshly crawled. Retain earlier snapshots, previous values and original chat
citations. Failed collection retains older evidence with its original timestamp. The UI exposes
source links, page/passage/cell locators, verbatim quotations, source context and revision changes.

Bind model chats to a registry ID, variant and market. Every request freezes the server-computed
comparison packet on the run. The Competitor Agent answers first from this preloaded evidence;
follow-ups cannot silently rescope the conversation from free text. The final-answer call introduced
by decision 0026 receives the same frozen comparison context as the agent-selection calls. A manually added model without
a BMW dataset line uses `EXTERNAL`, never an unfiltered internal-data scope.

## Consequences

- A successful request can have partial coverage; that is visible and not filled with invented data.
- Source extraction is evidence for human verification, not a guarantee that an OEM claim is true.
- Current offerings can differ from the supplied catalog. Provenance and intervals remain visible.
- Research/validation stays inside a bounded HTTP request, avoiding untracked serverless work.
- RLS is enabled without public policies on the comparison tables. API authentication remains required.
- Changes to the selected cohort affect new calculations and new chats; saved run packets remain frozen.
