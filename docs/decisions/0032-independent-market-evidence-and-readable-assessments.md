# 0032 — Preserve independent market evidence and readable assessments

> Date: 2026-10-11 · Status: accepted · Amends [0030](0030-feature-specific-and-public-market-evidence.md)

## Context

The two backend assessments loaded independently, but the frontend only combined public directions while an internal
response was available. A valid public risk disappeared if internal feedback was slow or unavailable. One failed
regional web search also failed the complete public request. Reasons and citations shared a narrow sidebar with
manual share inputs, which made it difficult to distinguish evidence from assumptions.

## Decision

Build map directions across all four markets from whichever backend results are available. Positive and negative
signals remain mixed; public evidence alone can color the map. Show pending, unavailable and partial coverage
explicitly. Retry each evidence source independently, preserving the successful response and any share assumptions.

Isolate each public regional search failure. Return successful verified results with per-market completion status,
sanitized gap explanations and notes. Do not cache partial results. An interpretation error retains verified public
feature mentions as general context instead of inventing directional evidence. A complete provider outage still
returns the existing sanitized 503. General quotes stay within one fetched page block, and a first-person "us" does
not prove United States geography. Private feedback remains local; public research receives only public queries and
fetched public page text. There are no database or authentication changes.

Expose reviewed sample counts for benefit/demand, risk and unclear from the internal backend. Keep those separate
from exact topic-match totals and whole-row polarity. Do not count the noun "comfort" as praise of comfort seats;
requests for better operation and explicit lack of need indicate risk. The local rules remain a disclosed,
conservative sample interpretation and can miss paraphrases.
Mixed comments show both feature passages in a single verbatim excerpt when they fit; longer spans explicitly
direct the reader to the source for both signals. A mixed comment contributes to both benefit and risk counts.

Move the selected market's evidence into a wide section below the map, with internal and public panels side by side
on desktop and stacked on mobile. Give each passage a stance, reason and source. Show combined reasoning, coverage
and method limits separately from optional numeric share inputs. Amber identifies trade-offs. A manual share change
explicitly labels the map as showing the user's assumption. Export includes source completion status.

## Verification

Regression checks exercise public-first results, internal outages, partial regional searches, source-specific retries,
malformed interpretations, stale replies, source quotations, negation and geography. Browser checks cover desktop
and mobile layouts, keyboard controls, source opening, export, share arithmetic, accessibility and overflow. Live
read-only checks use the configured database and public research provider; no internal feedback is sent externally.
