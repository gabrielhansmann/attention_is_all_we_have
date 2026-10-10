# 0003 — Add a Critic Agent; split Competitor from Market/Trend

> Date: 2026-10-10 · Status: accepted

## Context

Original agent roster had one "Market & Competitor Agent" and relied entirely on `evidence_level`
grading plus the PM's own judgment to catch weak or unsupported claims. A reference architecture
sketch (layered component view, not authored in this repo) proposed two changes worth adopting.

## Decision

1. **Add a Critic Agent** that sits between every agent and the PM review queue: verifies every
   claim has a live citation, forces a retry on anything unsupported, and downgrades
   `evidence_level` on thin-but-technically-cited claims — *before* the PM ever sees the output.
2. **Split Competitor from Market/Trend** into two agents. Competitor findings are close to
   verifiable fact (a rival ships a feature or it doesn't); market/trend findings are inherently
   speculative (what will 2030 customers want). Keeping them separate keeps that evidence-character
   difference visible on each requirement's assumptions, instead of averaging it away inside one
   "market research" blob.

## Consequences

- One more agent in the roster, but it directly cheapens "push back on agent results" for the PM —
  obviously weak output is caught before it reaches a human.
- Assumptions/uncertainties on a requirement can now distinguish "this rests on a competitor fact"
  from "this rests on a trend guess."

See [`../architecture/01-agents.md`](../architecture/01-agents.md).
