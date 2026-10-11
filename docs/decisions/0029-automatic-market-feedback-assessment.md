# 0029 — Assess feature feedback automatically when an option is selected

> Date: 2026-10-11 · Status: accepted, amended by [0030](0030-feature-specific-and-public-market-evidence.md) · Amends [0028](0028-market-impact-scenarios.md)

## Context

The first market map only loaded catalog equipment and waited for manually entered share changes. Selecting a
feature never ran an assessment, leaving the map unassessed and failing the expected selection-to-result workflow.
The source data has customer comments and equipment availability, but no validated model of feature-driven share.

## Decision

Add protected `POST /api/market-impact/assessment` with either a catalog option UUID or a custom feature and a vehicle
line. Resolve catalog labels on the backend and use a read-only local assessment agent over knowledge tools.
Match exact names and explicit German/English functional synonyms; unknown names remain exact phrases. Matching is
boundary-aware and literal, with all SQL parameters bound. No customer feedback, feature query, or catalog label is
sent to an external model by this assessment.

Compute direction from exact recorded-polarity counts over all matching comments: praise plus requests greater than
complaints gives a positive signal; fewer gives negative; equality gives mixed. No matching comments gives
insufficient evidence. Return a bounded, balanced sample of real citations, not fabricated sources. Clearly state
that complaints can include missing equipment and that topic matches do not identify exact option variants. Neither
counts nor polarity establish causal impact or numeric market share.

Catalog selection triggers the request automatically; custom text uses Assess feature to avoid requests while
typing. Render loading, error/retry, source quotations, exact matched counts, and distinct reasons for no market
coverage versus no topic match. Cache by line and feature in view memory, abort old requests, and discard late
responses. Apply automatic directions only where a PM has not entered a numeric scenario. An explicit scenario
overrides that market's color. Exclusion shows zero effect while preserving the recorded assessment.

## Consequences

The map produces evidence-backed directions after selection and remains honest about coverage gaps, including
China's absent feedback. Users can inspect the sources and retain assessments with their exported scenarios.
Topic matching has limited synonyms and may miss paraphrases; no-match results remain visible rather than being
silently filled. A future causal forecast requires validation and separate authorization for any external processing.
There is no schema migration. Updates are reflected in architecture 11 and 12 and the frontend guide.
