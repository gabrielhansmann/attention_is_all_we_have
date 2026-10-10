# Agents

> Status: `building` · Last updated: 2026-10-10 (all roster agents implemented and run by the step runner, see decisions [0014](../decisions/0014-all-roster-agents-implemented.md) and [0015](../decisions/0015-step-runner-and-step-output-on-the-step.md))

Every agent reads some slice of evidence and produces either new evidence (`Finding`s) or a
synthesis of existing evidence (`Cluster`, `Requirement`, `Score`, dossier). None of them change a
requirement's status, priority tier, or scope on their own — see
[`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md) for how
their output actually gets used.

## Roster

| Agent | Stage | Reads | Produces |
|---|---|---|---|
| Baseline Agent | 01 Situation analysis | Previous-gen feedback, BMW portfolio docs, prior sales trend | Findings tagged `strategic_continuity` |
| Customer Feedback Agent | 01 | `*_feedback_hackathon.xlsx`, `*_customer_studies.xlsx` | Findings (`complaint` / `unmet_need` / `praise`), each with sample size + market |
| Sales & Portfolio Agent | 01 | `sales_volumes.xlsx`, parsed OptionList rows | Revealed-preference findings — option uptake % as a `business_signal` input |
| Competitor Agent | 01 | Live web search — competitor spec pages, reviews, teardown data | Findings tagged `competitor_advantage`, source-trust tier |
| Market & Trend Agent | 01 | Live web search — trend reports, forward-looking analyst pieces | Findings tagged `market_trend`; explicitly flagged as assumption-heavy, not fact |
| Clustering / Ontology Agent | 02 | All findings across sources | Deduplicated clusters mapped onto the domain taxonomy |
| Critic Agent | cross-cutting | Any agent's draft output before it reaches the PM | Verifies every claim has a live citation; flags unsupported or weakly-sourced statements and forces a retry before the step reaches `awaiting_review` |
| Requirements Drafting Agent (Synthesizer) | 03 | Clusters + linked findings | Draft requirement: description, metric, acceptance criteria |
| Prioritization Agent | 04 | Draft requirements + findings + sales/option data | Score + weight breakdown + one-line rationale |
| Documentation Agent | 05 | Every accepted step + every PM decision in a run | Human-readable dossier (markdown), re-embedded into the knowledge layer |
| Delta / Tracking Agent | ongoing | New ingestion batches vs. existing requirement evidence | `new evidence` / `contradicting` / `stale` flags, routed to PM review |

Competitor and Market/Trend are kept as **two separate agents**, not one: competitor findings are
closer to verifiable fact (a rival ships a feature or doesn't), while trend findings are inherently
speculative (what will 2030 customers want). Collapsing them into one "market research" agent was
the original shape of this design — splitting them keeps that evidence-character difference
visible in each requirement's assumptions. See
[`decisions/0003-critic-agent-and-agent-split.md`](../decisions/0003-critic-agent-and-agent-split.md).

How the Competitor Agent decides *which* rivals to look at and makes their evidence comparable is
its own doc: [`10-competitor-benchmarking.md`](10-competitor-benchmarking.md).

## Implementation status

Every roster agent has a module in [`backend/app/agents/`](../../backend/app/agents/), runnable as
`python -m app.agents.<module>` with a `--dry-run` path, and tests that need no OpenAI, web or database.
A run calls them through `orchestration/agents.py` and the step runner, always behind the Critic
([decision 0015](../decisions/0015-step-runner-and-step-output-on-the-step.md)); the runner keeps the output on
the step and does not use the agents' own `store_result`, which is tested against a fake connection only. Where a
doc left a point open, the choice made is in
[decision 0014](../decisions/0014-all-roster-agents-implemented.md).

| Agent | Module | Model use |
|---|---|---|
| Baseline Agent | `baseline_agent.py` | drafts wording against indexed evidence |
| Customer Feedback Agent | `customer_feedback_agent.py` | drafts wording; signal type follows the cited comments' polarity |
| Sales & Portfolio Agent | `sales_portfolio_agent.py` | none for findings (optional: search terms for options) |
| Competitor Agent | `competitor_agent.py` | web search and extraction; bands, filters and comparison in code |
| Market & Trend Agent | `market_trend_agent.py` | web search and extraction |
| Clustering Agent | `clustering_agent.py` | proposes themes; code validates membership and domain |
| Critic Agent | `critic_agent.py` | none (optional injected support check, downgrade only) |
| Requirements Drafting Agent | `requirements_drafting_agent.py` | drafts statements; each must cite cluster findings |
| Prioritization Agent | `prioritization_agent.py` | none |
| Documentation Agent | `documentation_agent.py` | none |
| Delta / Tracking Agent | `delta_tracking_agent.py` | none |

The **Market & Trend Agent**
([`market_trend_agent.py`](../../backend/app/agents/market_trend_agent.py)) was the first and is the pattern
the others follow:

- reads PM scope (`vehicle_line`, `market`) plus a research query
- searches the web through the LLM's built-in search tool (OpenAI Responses API `web_search`, no
  separate search API; see [decision 0009](../decisions/0009-web-search-through-the-llm.md)), or uses
  local `--seed-sources` fixtures for deterministic tests
- takes each source's URL and title from the search tool's citation annotations, never from text
  the model wrote; an uncited statement produces no source
- extracts cited `market_trend` findings, keeping URL + retrieval date as the locator
- stores web source metadata (`input_family = website`, channel/domain, origin `agent_search`,
  language where known, trust tier, ingest report)
- assigns evidence from source trust tier (`oem` → `Verified`, `trade_press` → `Interpreted`,
  `forum_social` → `Unverified`)
- stores a snapshot and explicit assumptions on each finding. For searched sources the snapshot is
  the model's cited summary of the page, not a verbatim quote from it
- routes pricing, regulatory/type-approval and engineering-internal claims to the visible
  out-of-scope bin via `finding.out_of_scope_reason`
- leaves the step in `awaiting_review`; it does not accept, reject, score, prioritize or draft
  requirements on its own

The implementation is intentionally testable without external services: `--seed-sources`,
`--draft-json` and `--dry-run` exercise the Source → Finding path without OpenAI, web access or
Supabase.

## The Critic Agent

The Critic doesn't sit at a stage of its own — it sits between every agent and the PM. Before any
step reaches `awaiting_review`, the Critic Agent:

1. Checks that every factual claim in the agent's output links to a real source with a locator
   (page/row for provided files, URL + retrieval date for web sources).
2. Flags claims that don't — the step is automatically sent back for a retry (same agent, same
   scope, instructed to either find a citation or drop the claim) *before* the PM ever sees it.
3. Downgrades `evidence_level` on anything that's technically cited but thin (single source, no
   corroboration, low source-trust tier) rather than silently passing it through at full confidence.

This is what makes "push back on agent results" cheap for the PM: obviously weak output never
reaches the review queue in the first place. The PM still pushes back on anything the Critic let
through but the PM disagrees with — that's a normal `Retry` or `Reject` action on the step, see
next doc.

## Orchestrator

Not an agent that produces findings. It does three things:

1. **Chooses.** Reads the PM's chat request and picks the next agent to call, with a one-line
   reason that is shown in the chat.
2. **Reads.** After each agent it sees the result (summary, finding count, success or failure) and
   decides whether another agent is needed or the request is answered. Code refuses calls that break
   the pipeline rules (unknown agent, already run, earlier stage missing).
3. **Sequences.** Runs the loop and the `PipelineRun`/`Step` records (see next doc), passing the
   output of successful steps to later agents as context. A step is never re-run.

Not every request uses every agent. See
[`02-orchestration-and-human-in-the-loop.md`](02-orchestration-and-human-in-the-loop.md) and
[decision 0005](../decisions/0005-chat-entry-and-orchestrator-planned-steps.md).
