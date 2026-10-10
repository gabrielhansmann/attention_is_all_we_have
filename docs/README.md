# Requirement Evidence Engine — living architecture docs

Start with the [software idea](idea.md) for the original model-specific product concept:
vehicle specifications, PM priorities and successor targets, competitor comparisons by market,
historical trends, weekly reports, and AI suggestions grounded in cited evidence.

Technical architecture for the BMW "AI for Product Decision Making" hackathon challenge: a
multi-agent system that turns customer feedback, product data, sales data and web research into
cited, PM-approved customer requirements for a successor vehicle.

These docs are **living** — they change as we build. When a design decision changes, edit the
relevant file in place and add a dated entry to [`decisions/`](decisions/) explaining what
changed and why, instead of leaving the old reasoning to rot silently in a doc that still reads
as current.

## Status legend

Each doc opens with a status line:

- `draft` — shape is proposed, not yet validated against real data or code
- `building` — actively being implemented, may lag the code slightly
- `stable` — implemented and not expected to change before the demo

## Map

| Doc | What it answers |
|---|---|
| [`idea.md`](idea.md) | The original software concept and the PM's model-specific decision loop |
| [`architecture/00-overview.md`](architecture/00-overview.md) | What is this, in scope / out of scope, the five-stage pipeline at a glance |
| [`architecture/01-agents.md`](architecture/01-agents.md) | Every agent: what it reads, what it produces, how autonomous it is |
| [`architecture/02-orchestration-and-human-in-the-loop.md`](architecture/02-orchestration-and-human-in-the-loop.md) | **How the PM actually stays in control** — the chat → orchestrator plan → review-and-accept-each-agent model |
| [`architecture/03-ingestion.md`](architecture/03-ingestion.md) | How a PDF or Excel file becomes a cited `Finding` |
| [`architecture/04-data-model.md`](architecture/04-data-model.md) | Every entity and how they reference each other |
| [`architecture/05-requirement-lifecycle.md`](architecture/05-requirement-lifecycle.md) | What happens to a requirement after it's accepted, over the ~2-year program |
| [`architecture/06-prioritization.md`](architecture/06-prioritization.md) | The scoring formula and a worked example |
| [`architecture/07-audit-trail.md`](architecture/07-audit-trail.md) | The event log schema that makes everything traceable |
| [`architecture/08-scaling-and-config.md`](architecture/08-scaling-and-config.md) | Why this isn't hardcoded to one vehicle line or market |
| [`architecture/09-tech-stack.md`](architecture/09-tech-stack.md) | What we're actually building it with, and why |

| [`architecture/10-competitor-benchmarking.md`](architecture/10-competitor-benchmarking.md) | How one BMW becomes a comparable rival set, and how rival evidence is compared fairly |
| [`architecture/11-knowledge-layer.md`](architecture/11-knowledge-layer.md) | How the evidence is normalized, stored with citations, and queried by the agents |
| [`architecture/12-repo-structure.md`](architecture/12-repo-structure.md) | How the repo is split into backend and frontend, the API, and the rules between them |
| [`frontend-style-guide.md`](frontend-style-guide.md) | How the UI is built: tokens, layout patterns, shadcn MCP and design-skill workflow, Playwright review loop, pitfalls |

## Functional requirements

The [frontend guide](../frontend/README.md) documents the delivered PM workspace, local setup,
verification, Vercel hosting, and its explicit demo-data/backend limitations.

What the system must do, as testable statements with IDs and priorities, in
[`requirements/`](requirements/) — partly derived from the architecture docs above, partly new
(PM overview, flexible feedback / website / social media inputs). Start at
[`requirements/README.md`](requirements/README.md).

## Decision log

Dated, append-only records of the choices that weren't obvious, in [`decisions/`](decisions/).
Same philosophy as the product itself: a decision without a recorded reason is a decision nobody
can push back on later.

## Source material

- Official brief: `BMW_Hackathon_Briefing_Short.pdf` (provided by BMW, kept outside this repo)
- Provided data: `F70`/`G60`/`G70` feedback, option lists, customer studies, `sales_volumes.xlsx`
  (presumed mapping: F70 → 1 Series successor, G60 → 5 Series, G70 → 7 Series — **confirm against
  BMW's codebook before stating this as fact**)
- A rendered, presentation-friendly version of the pipeline/data-model/lifecycle diagrams in this
  doc set exists as a standalone artifact for pitching; these `.md` files are the source of truth
  for building.
