# 0030 — Combine feature-specific feedback with verified public evidence

> Date: 2026-10-11 · Status: accepted · Amends [0029](0029-automatic-market-feedback-assessment.md)

## Context

The directional assessment counted overall feedback polarity as an option verdict. A real G60 wheel comment
praised 19-inch wheels but complained about dashboard controls; its negative row label incorrectly opposed the
wheels. Several rows repeated the same text. Complaints about missing equipment can express demand, while defects
indicate implementation risk rather than rejection of the feature itself. The PM also requested public web research.

A live public search then produced unsupported regional summaries: a report about BMW India was described as
Chinese customer evidence, and commercial shopping guides were counted as customer research. URL citations alone
do not verify the contents of generated search summaries.

## Decision

Deduplicate normalized comment text within each line/market before counting and sampling. Interpret feature-specific
clauses locally using conservative, disclosed rules; preserve unclear passages. Whole-comment polarity counts are
retrieval metadata and do not determine option direction. The bounded sample's benefits and risks are both retained:
any of each means mixed rather than hiding a minority risk by voting. These are interpretations, not a population
survey, causal model, or market-share forecast.

Add an independent protected public-research endpoint. Catalog searches use a static vocabulary of generic public
feature functions; an unmapped catalog label remains local and produces a visible gap. Custom feature text is the
PM's public query. No private feedback, IDs, metadata, counts or catalog label is sent to the public model. Reuse
Responses API web search and its URL annotations, then fetch candidate pages through the existing DNS/redirect-checked
reader. Classify only retrieved public page text. Every accepted excerpt must occur verbatim in the fetched page,
be at most 25 words, mention the feature, and retain its actual source URL and retrieval date. A directional market
claim needs a verbatim source geography passage. Reject shopping sites; keep promotional availability and social
anecdotes as context. A single other-country page cannot represent heterogeneous rest of world. Unreadable pages
and unsupported claims become evidence gaps. URLs and excerpts are verified; model relevance/stance still needs PM
judgment and is explicitly labeled as interpretation.

Render public and internal requests independently with source links, loading, outage/retry, distinct gap reasons,
cache and stale-response handling. Combining contrary signals yields trade-offs, not an average score. A public
provider failure preserves internal results. Manual numeric scenarios remain explicit assumptions and take precedence;
export includes all evidence and assumptions. There are no schema changes. Backend public results have a bounded
15-minute in-process cache, provider timeouts and no automatic retries.

## Consequences and verification

The wheel example now counts four distinct comments and evaluates their wheel passages rather than dashboard
complaints. Web claims must survive fetched-page and geography checks. The UI distinguishes potential benefits from
implementation/acceptance risks. No process can infer a numeric or causal share effect from these sources alone.
Rules may miss paraphrases, sampling may omit relevant comments, and site access restrictions may leave public gaps.
Regression checks cover mixed-topic feedback, missing-feature demand, duplication, conflicting signals, fabricated
excerpts, geography, commercial/manufacturer context, external outages and late replies.

Web API citation behavior follows [official OpenAI documentation](https://developers.openai.com/api/docs/guides/tools-web-search).

Verified feature mentions without directional market support appear separately as general web context, with
short page excerpts and source links. They never color a market or fill its evidence gap.
