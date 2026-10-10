# 0026 — The orchestrator writes the final answer to the PM

> Date: 2026-10-11 · Status: accepted · Builds on [0018](0018-orchestrator-decides-in-an-agentic-loop.md)

## Context

Renumbered from 0023 when integrating main: that number was already assigned to file uploads.
Decision IDs must remain unique because the Supabase documentation mirror upserts by ID.

The final result in the chat was the agents' own summaries stitched together (or the whole dossier). The PM saw the
same text twice, with raw citation strings and no judgement about what mattered. The orchestrator already reads every
result to decide the next call, but it never spoke to the PM about them.

## Decision

When the loop finishes, `Orchestrator.answer` writes the reply in the orchestrator's own words: the direct answer
first, the few points that matter most with how well the evidence backs them, what is uncertain or missing, and a
suggested next step. It reads each accepted step's summary and its cited findings (id and text) and cites findings by
id. Code removes any citation id the model invented, and the reply is skipped when no step succeeded.

If the model fails or the orchestrator has no model (`RuleOrchestrator`), the thread falls back to the previous
compiled summaries. The message payload records `written_by` (`orchestrator` or `summaries`) and `dossier` (whether a
Documentation Agent step was accepted). The dossier stays under Dossiers; it is no longer pasted into the chat.

## Consequences

One extra model call per finished run. The reply is only as good as the findings it is given and is capped at about
180 words. The Critic does not review it, so its citations are limited to ids the agents produced.
