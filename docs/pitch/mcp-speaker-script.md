# BMW Product Intelligence: MCP presentation

Source snapshot: `0fa94c3`. Six main slides, three hidden Q&A slides; 180 seconds allocated.

Built and edited through the PowerPoint MCP. Timings are rehearsal targets, not measured results.

## Slide 1: Which customer needs shape the next vehicle?

**Timing:** 0:00–0:20

Imagine you're defining the successor to a vehicle. Customer complaints sit in spreadsheets, equipment details in PDFs, and competitor claims across the web. How do you turn that evidence into a requirement you can defend? That's the question behind BMW Product Intelligence.

**Delivery cue:** Open with the question. Pause before introducing the project.

**Claim boundary:** Product problem and intended outcome; no claim of measured time savings.

**Sources:**

- [docs/idea.md](../../docs/idea.md)
- [docs/architecture/00-overview.md](../../docs/architecture/00-overview.md)
- [docs/requirements/README.md](../../docs/requirements/README.md)

## Slide 2: A shared evidence base. Every source stays traceable.

**Timing:** 0:20–0:50

The provided BMW files are already loaded into a shared evidence base: over thirteen thousand customer comments, plus customer studies, product catalogs, equipment options, and sales. Retrieval keeps the original file and location. Markets remain separate, and coverage gaps stay visible. For example, China has study and sales data, but no customer feedback in this dataset.

**Delivery cue:** Let the audience read the large number. Do not read every statistic aloud.

**Claim boundary:** Documented loaded-data snapshot: 13,771 comments, 1,627 study cells, 198 equipment options, 149 catalog passages, 36 sales records. Study cells are not respondents. China has zero customer feedback in this dataset.

**Sources:**

- [docs/architecture/03-ingestion.md](../../docs/architecture/03-ingestion.md)
- [docs/architecture/11-knowledge-layer.md](../../docs/architecture/11-knowledge-layer.md)
- [docs/decisions/0007-option-availability-and-ontology-seed.md](../../docs/decisions/0007-option-availability-and-ontology-seed.md)
- [docs/decisions/0008-knowledge-layer-normalization-and-retrieval.md](../../docs/decisions/0008-knowledge-layer-normalization-and-retrieval.md)
- [backend/app/knowledge/library.py](../../backend/app/knowledge/library.py)

## Slide 3: AI proposes. The PM decides.

**Timing:** 0:50–1:25

The PM starts with a question: what should improve for the next G sixty in the US? The planner chooses relevant agents and explains why. The backend runner now executes them behind Critic checks, and supports four PM actions: accept, edit, retry, or reject. Acceptance starts the next step using accepted evidence. The live frontend currently shows planning; connecting its review controls is the next integration.

**Delivery cue:** Explain the backend workflow, then distinguish it from the current frontend. Say G sixty naturally.

**Claim boundary:** The runner and step-action endpoints are implemented and fixture-tested. Every agent passes through Critic checks with one automatic retry. The frontend does not call these execution endpoints yet. Edit changes the summary only. Full live execution was not validated for this presentation.

**Sources:**

- [docs/architecture/02-orchestration-and-human-in-the-loop.md](../../docs/architecture/02-orchestration-and-human-in-the-loop.md)
- [docs/decisions/0005-chat-entry-and-orchestrator-planned-steps.md](../../docs/decisions/0005-chat-entry-and-orchestrator-planned-steps.md)
- [docs/decisions/0012-planner-proposes-code-validates.md](../../docs/decisions/0012-planner-proposes-code-validates.md)
- [docs/decisions/0013-frontend-uses-only-the-backend-api.md](../../docs/decisions/0013-frontend-uses-only-the-backend-api.md)
- [backend/app/orchestration/catalog.py](../../backend/app/orchestration/catalog.py)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 4: Every priority has a reason.

**Timing:** 1:25–2:00

The output is designed to be a requirement with supporting sources, a defensible target, and explicit assumptions. In the prototype, the PM can inspect and change the scoring components: customer relevance, business signal, strategic fit, and effort. Confidence stays separate from priority. A promising idea with thin evidence must look different from a well-supported one. Decisions carry reasons, so the review can be explained later.

**Delivery cue:** Emphasize that confidence and priority answer different questions. Avoid presenting illustrative scores as validated recommendations.

**Claim boundary:** Cited retrieval, agent scoring and step audit events exist. The UI demonstrates editable scoring on fixtures. The runner retains outputs on steps, not in finding, requirement or score backlog tables. Business signal can use catalog-standard availability as an explicitly thin proxy; it is not observed customer option uptake.

**Sources:**

- [docs/architecture/04-data-model.md](../../docs/architecture/04-data-model.md)
- [docs/architecture/06-prioritization.md](../../docs/architecture/06-prioritization.md)
- [docs/architecture/07-audit-trail.md](../../docs/architecture/07-audit-trail.md)
- [docs/requirements/03-requirements-and-prioritization.md](../../docs/requirements/03-requirements-and-prioritization.md)
- [docs/decisions/0011-local-demo-frontend-and-vercel.md](../../docs/decisions/0011-local-demo-frontend-and-vercel.md)
- [frontend/src/data.ts](../../frontend/src/data.ts)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 5: A working foundation. A clear next step.

**Timing:** 2:00–2:35

Today, ingestion, cited retrieval and live planning work. The backend also has the agent modules, step runner, Critic checks, and PM review endpoints. These additions are fixture-tested; their full live path is not yet validated. The public workspace shows targets, reviews and reports on labeled sample data. Next, connect the live frontend and persist accepted outputs into the requirement backlog. The foundation is inspectable without treating demo decisions as verified BMW recommendations.

**Delivery cue:** Point to the real workspace screenshot. Distinguish implemented backend code from verified live operation and the public sample-data demo.

**Claim boundary:** All roster modules and the backend runner are implemented per ADRs 0014 and 0015. The new agents were tested with fixtures, not validated end to end against the live services. The runner writes JSON outputs to steps and audit events; it does not write accepted requirements to backlog tables. Public Vercel remains a static fixture demo.

**Sources:**

- [frontend/README.md](../../frontend/README.md)
- [docs/decisions/0011-local-demo-frontend-and-vercel.md](../../docs/decisions/0011-local-demo-frontend-and-vercel.md)
- [docs/decisions/0013-frontend-uses-only-the-backend-api.md](../../docs/decisions/0013-frontend-uses-only-the-backend-api.md)
- [docs/architecture/01-agents.md](../../docs/architecture/01-agents.md)
- [docs/decisions/0009-web-search-through-the-llm.md](../../docs/decisions/0009-web-search-through-the-llm.md)
- [backend/app/agents/market_trend_agent.py](../../backend/app/agents/market_trend_agent.py)
- `frontend/src/lib/live.ts` (historical file at source snapshot `0fa94c3`; removed by [decision 0023](../decisions/0023-database-backed-workspace.md))
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 6: Pilot one vehicle line. Make the decision traceable.

**Timing:** 2:35–3:00

Our next step is a pilot on one vehicle line and market. Connect the live workspace and backlog, then measure time to a cited draft, evidence coverage, and PM review effort. The goal is a faster path to requirements the PM can defend, with the evidence and decisions attached. Thank you.

**Delivery cue:** Close on the pilot proposal. These are proposed evaluation measures, not results already achieved.

**Claim boundary:** Pilot and evaluation measures are this pitch's proposal, inferred from the documented PM goals. No customer adoption, ROI, accuracy or time-savings result is claimed. Recurring evidence refresh, weekly reports, broader inputs and long-term tracking are roadmap items.

**Sources:**

- [docs/idea.md](../../docs/idea.md)
- [docs/architecture/05-requirement-lifecycle.md](../../docs/architecture/05-requirement-lifecycle.md)
- [docs/architecture/08-scaling-and-config.md](../../docs/architecture/08-scaling-and-config.md)
- [docs/requirements/04-pm-overview.md](../../docs/requirements/04-pm-overview.md)
- [docs/requirements/06-lifecycle-and-configuration.md](../../docs/requirements/06-lifecycle-and-configuration.md)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 7: One evidence layer. A backend the PM can inspect.

**Timing:** Q&A only

React calls FastAPI through /api. Shared knowledge tools combine hybrid search with exact structured lookups and row-based citations. Supabase Postgres and pgvector store evidence, plans, steps and audit events. The in-process background runner calls agent adapters behind Critic checks. Outputs live on the step and only accepted outputs reach later agents. Frontend execution wiring, backlog writes and recovery from server interruption are still pending.

**Delivery cue:** Use only in Q&A. Explain exact data versus semantic retrieval, rather than listing technologies.

**Claim boundary:** Backend runner and Critic checks implemented in ADR 0015. No durable execution recovery exists; interrupted background work can remain stuck. LangGraph/checkpointed execution remains planned. Agents read evidence through the shared knowledge tools.

**Sources:**

- [docs/architecture/03-ingestion.md](../../docs/architecture/03-ingestion.md)
- [docs/architecture/09-tech-stack.md](../../docs/architecture/09-tech-stack.md)
- [docs/architecture/11-knowledge-layer.md](../../docs/architecture/11-knowledge-layer.md)
- [docs/architecture/12-repo-structure.md](../../docs/architecture/12-repo-structure.md)
- [docs/decisions/0001-two-tier-pdf-ingestion.md](../../docs/decisions/0001-two-tier-pdf-ingestion.md)
- [docs/decisions/0010-frontend-backend-repo-structure.md](../../docs/decisions/0010-frontend-backend-repo-structure.md)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 8: Evidence is uneven. We show the gaps.

**Timing:** Q&A only

The documented customer-feedback coverage is 8,783 US comments, 3,292 European comments, 1,696 from the rest of the world, and zero from China. China still has studies and sales. There are 2,666 comments without a mapped domain, and the customer-study cells have no respondent counts. The 2030 sales values are forecasts. Competitor benchmarking is designed to compare the same market, source type and measurement standard; the competitor module exists, while full live validation is pending.

**Delivery cue:** Use only in Q&A. A zero is a data-coverage gap, not proof that customers have no unmet needs.

**Claim boundary:** Documented coverage snapshot, not unique customers or a representative population. The competitor module now exists per ADR 0014, but full live validation is pending. Preserve assumptions about market and vehicle-line mappings; confirm them with BMW. Likes and reach are not respondent counts.

**Sources:**

- [docs/architecture/11-knowledge-layer.md](../../docs/architecture/11-knowledge-layer.md)
- [docs/architecture/10-competitor-benchmarking.md](../../docs/architecture/10-competitor-benchmarking.md)
- [docs/decisions/0008-knowledge-layer-normalization-and-retrieval.md](../../docs/decisions/0008-knowledge-layer-normalization-and-retrieval.md)
- [docs/requirements/01-inputs-and-ingestion.md](../../docs/requirements/01-inputs-and-ingestion.md)
- [docs/requirements/02-analysis-and-structuring.md](../../docs/requirements/02-analysis-and-structuring.md)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)

## Slide 9: What works today. What comes next.

**Timing:** Q&A only

Ingestion, cited retrieval and live planning work. All roster agents and a backend runner with Critic checks and PM actions are implemented and fixture-tested. The public frontend still shows sample-data reviews. Next are live frontend wiring and writing accepted results into the requirement backlog. Outputs currently stay on steps. Durable execution recovery and recurring refresh remain roadmap items. No measured time saving, recommendation accuracy or customer adoption is claimed.

**Delivery cue:** Use only in Q&A. Implemented code is distinct from live-service validation. Explain step output versus backlog persistence.

**Claim boundary:** ADRs 0014 and 0015 supersede the old Market-only agent and no-runner status. The frontend does not call execution endpoints. Agent store_result methods were not live-validated. The runner deliberately avoids backlog writes. No restart recovery or production worker model is shipped.

**Sources:**

- [docs/architecture/01-agents.md](../../docs/architecture/01-agents.md)
- [docs/architecture/02-orchestration-and-human-in-the-loop.md](../../docs/architecture/02-orchestration-and-human-in-the-loop.md)
- [docs/architecture/12-repo-structure.md](../../docs/architecture/12-repo-structure.md)
- [docs/decisions/0003-critic-agent-and-agent-split.md](../../docs/decisions/0003-critic-agent-and-agent-split.md)
- [docs/decisions/0009-web-search-through-the-llm.md](../../docs/decisions/0009-web-search-through-the-llm.md)
- [docs/decisions/0012-planner-proposes-code-validates.md](../../docs/decisions/0012-planner-proposes-code-validates.md)
- [docs/decisions/0013-frontend-uses-only-the-backend-api.md](../../docs/decisions/0013-frontend-uses-only-the-backend-api.md)
- [docs/requirements/05-pm-control-and-traceability.md](../../docs/requirements/05-pm-control-and-traceability.md)
- [docs/requirements/06-lifecycle-and-configuration.md](../../docs/requirements/06-lifecycle-and-configuration.md)
- [docs/decisions/0014-all-roster-agents-implemented.md](../../docs/decisions/0014-all-roster-agents-implemented.md)
- [docs/decisions/0015-step-runner-and-step-output-on-the-step.md](../../docs/decisions/0015-step-runner-and-step-output-on-the-step.md)
