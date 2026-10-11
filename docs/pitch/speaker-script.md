# BMW Product Intelligence: speaker script

Six pitch slides, followed by three Q&A slides. Rehearsal target: three minutes; no measured product performance is claimed.

Data snapshot: 2026-10-10T21:01:22.195974+00:00. Deployed main: `7c7ba86`.

## Slide 1: Which customer needs should shape the next vehicle?

**Timing:** 0:00 - 0:25

A product manager has a customer question, but the answer is scattered across feedback files, studies, catalogs and market research. BMW Product Intelligence brings those sources into one evidence layer and runs a cited research conversation. The goal is a defensible customer-facing decision. The current delivery is a research prototype; the approved requirement backlog remains a next step.

**Claim boundary:** Product mission, not a measured business outcome. The deployed app is a research workspace, not a production approval system.

**Sources:**

- docs/architecture/00-overview.md
- docs/decisions/0017-minimal-live-only-frontend.md

## Slide 2: A real evidence base. Every number comes from Supabase.

**Timing:** 0:25 - 0:55

At this snapshot, Supabase holds 13,771 customer comments, 1,627 customer-study cells and 198 equipment options. The 198 text passages separate into 149 BMW catalog passages and 49 stored web passages. There are 8 internal source files and 3 web sources. These are loaded records, not unique customers, respondents or validated market recommendations.

**Claim boundary:** Counts describe the frozen snapshot, not unique customers. Study cells are not respondents. Stored web material has not all been validated for vehicle and market relevance.

**Sources:**

- docs/pitch/verified-data.json
- backend/app/knowledge/library.py
- backend/app/knowledge/tools.py

## Slide 3: Ask once. The orchestrator chooses the agents.

**Timing:** 0:55 - 1:30

The PM sends a scoped research question. The orchestrator chooses one agent, reads its result and decides whether another is needed. Code checks the prerequisites; the Critic checks citations before accepted output reaches later agents. The result and the reasons appear in the thread. The previous manual plan, start and per-step review controls are gone. A request does not need to run every stage.

**Claim boundary:** Describes shipped main code. No new authenticated hosted run was executed for this deck. Accepted means automatic runner/Critic acceptance, not PM approval.

**Sources:**

- docs/decisions/0018-orchestrator-decides-in-an-agentic-loop.md
- docs/decisions/0019-orchestration-loop-runs-on-langgraph.md
- backend/app/orchestration/loop.py
- frontend/src/features/research/LiveResearch.tsx

## Slide 4: The app is deployed. Its frontend and backend are connected.

**Timing:** 1:30 - 2:00

This is the actual public Vercel sign-in screen, without mocked data. The hosted JavaScript matches the main build. The public health endpoint reports a healthy database and an AI key configured on the server. Inside the authenticated app, the shipped views are Research, Evidence and Sources. Protected endpoints require a session. This presentation checked the public deployment and read Supabase directly; it did not exercise a new signed-in hosted workflow.

**Claim boundary:** Screenshot is real public Vercel UI. AI key configured is not an AI completion test. Authenticated hosted research, search and source-viewer interactions were not exercised.

**Sources:**

- docs/pitch/verified-deployment.json
- docs/pitch/assets/vercel-signin-desktop.png
- frontend/README.md
- frontend/src/App.tsx

## Slide 5: A concrete signal. A source the PM can inspect.

**Timing:** 2:00 - 2:35

This is a real database example, not an invented requirement. Under G60, US, Comfort and Space, the snapshot contains 396 comments, including 139 tagged negative. One comment says that reaching the heated steering wheel through climate options feels cumbersome and asks for a dedicated button. The exact workbook and row are preserved. The count covers the category; it does not mean 139 steering-wheel complaints or prove a recommended design.

**Claim boundary:** The quote is verbatim from one stored customer comment. Category counts are comment records, not people. No approved requirement, prevalence estimate or design recommendation is inferred.

**Sources:**

- docs/pitch/verified-data.json
- backend/app/knowledge/tools.py
- docs/decisions/0020-source-viewer-for-citations.md

## Slide 6: Pilot one vehicle line. Measure the value of cited research.

**Timing:** 2:35 - 3:00

The next step is a measured pilot on one vehicle line and market. Measure time to a cited answer, citation correctness and how much of the decision space the evidence covers. Validate the complete signed-in hosted run, then connect accepted outputs to a persistent requirement backlog. There is no measured time saving or recommendation accuracy yet. The app is available at the address on screen; an existing application account is required.

**Claim boundary:** Pilot metrics are proposed measurements, not achieved results. Requirement/backlog persistence and full authenticated hosted verification remain unfinished.

**Sources:**

- docs/pitch/verified-data.json
- docs/pitch/verified-deployment.json
- docs/architecture/02-orchestration-and-human-in-the-loop.md

## Slide 7: One evidence layer. A visible chain from source to answer.

**Timing:** Q&A only

React calls only FastAPI through /api. Backend knowledge tools retrieve exact structured rows and combine semantic and keyword search for narrative text. Supabase stores evidence, chat history, steps and audit events. LangGraph controls the loop, with its own Postgres checkpoints. The run still executes inside the API process. This Vercel package sets a five-minute function duration, so long research needs a durable worker model. Checkpoints alone do not prove reliable hosted background execution.

**Claim boundary:** Architecture follows deployed code, not a new execution test. Five minutes is the package configuration, not a universal Vercel limit. Durable workers are not shipped.

**Sources:**

- docs/decisions/0019-orchestration-loop-runs-on-langgraph.md
- backend/app/knowledge/tools.py
- docs/pitch/verified-deployment.json
- https://vercel.com/docs/functions/configuring-functions/duration

## Slide 8: Coverage is uneven. A source tag still needs review.

**Timing:** Q&A only

These are exact customer-comment counts by market. China has no customer-feedback comments in this dataset, although G68 and G70 have Chinese customer-study cells and sales data. G60 China is not an interchangeable scope for G68 China. A stored Genesis G70 web page has been tagged G70; the BMW vehicle code collision needs review before any competitor conclusion. Study cells are not respondents, and sales forecasts are not observed outcomes.

**Claim boundary:** Counts are not population estimates. G68 and G60 remain separate scopes. The Genesis/BMW G70 collision is visible in stored source metadata; no source rows were changed.

**Sources:**

- docs/pitch/verified-data.json
- backend/app/knowledge/library.py
- backend/app/knowledge/tools.py

## Slide 9: What the evidence proves. What still needs validation.

**Timing:** Q&A only

The public hosted frontend, database connection and protected-route boundary were verified. Main contains the live views, autonomous orchestrator, Critic and checkpoint code; this deck did not run a new authenticated hosted request. Supabase stores five completed runs and one older in-progress run with a planned step. Those history rows are not evidence of a successful fresh Vercel run. Findings, clusters, requirements and scores are still empty in their backlog tables. Original BMW files are absent from the deployed package, so hosted source-file download is unavailable. The presentation uses main and runtime evidence rather than feature-branch decisions mirrored in Supabase.

**Claim boundary:** No complete hosted workflow, performance benefit, approved requirement or reliable long-running worker is claimed. Source-context rows exist, but original BMW files were not uploaded.

**Sources:**

- docs/pitch/verified-data.json
- docs/pitch/verified-deployment.json
- docs/architecture/02-orchestration-and-human-in-the-loop.md
- docs/decisions/0020-source-viewer-for-citations.md
