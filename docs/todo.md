# To do: from built pieces to a working system

> Last updated: 2026-10-10

"Working" means: a PM signs in, asks a question for G60 × Europe, runs every agent step with
accept / retry / reject, and then sees the resulting requirements in the portfolio, read from the
database and not from fixtures.

## Where we are

- All roster agents exist as modules and are tested with fixtures only. None has run against the
  live database or a live model ([decision 0014](decisions/0014-all-roster-agents-implemented.md)).
- The step runner and its endpoints exist (`POST /api/runs/{id}/start`,
  `POST /api/steps/{id}/accept | retry | reject | edit`), but the frontend does not call them
  ([decision 0015](decisions/0015-step-runner-and-step-output-on-the-step.md)).
- A step's output is kept as JSON on the step. Nothing is written to `finding`, `cluster`,
  `requirement` or `score` by a run.
- The Requirements, Overview and Reports views run on demo fixtures. The API has no endpoints for
  them.

Tick a box when the item is merged. Phases 1 and 2 are the critical path. Once item 1 passes, item 2
(frontend) and items 4–5 (persistence) touch different code and can be done in parallel.

## Phase 1: one real run, end to end

- [x] **1. Smoke-test the agents live.** Done on 2026-10-10: all nine agents ran for G60 × Europe
  through the runner's adapters and the Critic, in memory, with nothing written to the database.
  Fixed: the Competitor Agent's rival lines had no citation, so the Critic always forced a retry
  and the retry came back empty; vehicle labels repeated make and model; the clustering prompt
  split themes by signal type. Left open:
  - [ ] **1a. Competitor Agent finds no advantage live.** Five live runs gave 0 findings. The one
    scoping search returns 2 to 5 sources for the anchor and all rivals together, so profiles are
    thin and rivals often miss the bands, and owner or expert comparisons need 3 mentions per side
    (`MIN_MENTIONS`) from at most 6 sources per vehicle.
  - [ ] **1b. `business_signal` is 0 on every score.** A requirement is scored only from the
    findings of its own cluster, and sales and option findings still end up in a cluster of their
    own. All four requirements came out as Tier 3.
  - [ ] **1c. The Critic's retry instruction is appended to the web-search prompt** of the
    Competitor and Market & Trend agents, where it does not belong.
  - [ ] **1d. Step summaries are long** (Drafting 17k characters, Documentation 24k, dossier 37k
    with 84 coverage gaps). The step card needs a short form.
  - [ ] **1e. Two backend tests fail against the shared database** (`test_only_a_hash_of_the_token_is_stored`,
    `test_conversations_list_most_recently_active_first`): they assert on exact table contents and
    see rows that are already there.
- [ ] **2. Wire the runner into the frontend.**
  - [ ] Add `startRun`, `acceptStep`, `retryStep`, `rejectStep`, `editStep` to
    `frontend/src/lib/api.ts`.
  - [ ] In `frontend/src/features/research/LiveResearch.tsx`: a Start button on the plan, polling of
    the conversation while a step is `running`, step cards with the four actions, the reject choice
    (proceed with a coverage gap or abort), and the final result.
  - [ ] Show the Critic's downgrades and dropped claims on the step card.
  - [ ] Extend the Playwright mocks in `frontend/tests/live.spec.ts`.
- [ ] **3. Recover stuck runs.** On startup or after a timeout, move steps left in `running` to
  `awaiting_review` as failed, so the PM can retry.

**Done when** a full run completes from the browser and shows the dossier.

## Phase 2: persist what the PM accepted

- [ ] **4. One migration for the known schema gaps.**
  - [ ] `source.type` allows `dossier`.
  - [ ] `score` gets columns for the weight vector and the breakdown.
  - [ ] `finding.signal_type` allows `competitor_weakness`, `strategic_continuity` and
    `business_signal`.
- [ ] **5. Persist on accept.** When a step is accepted, write its output to `finding`, `cluster`,
  `requirement`, `requirement_finding` and `score`, using the runner's finding ids. Make it
  idempotent, so a retry replaces links and leaves no stale ones.
- [ ] **6. Settle when a requirement enters the lifecycle.** Proposal: follow
  [doc 05](architecture/05-requirement-lifecycle.md) and persist at `draft` only when the
  Documentation step is accepted. Record the choice in `decisions/`.
- [ ] **7. Pass effort and themes from drafting to prioritization**, so a score no longer assumes
  medium effort.
- [ ] **8. Move the shared helpers** (`ensure_step`, evidence and citation types) into one module.

**Done when** the tables hold the accepted findings, requirements and scores with their citations
after a run.

## Phase 3: live portfolio

- [ ] **9. Backend endpoints**, all in the `protected` router.
  - [ ] `GET /api/requirements` (filters, score breakdown, citations) and
    `GET /api/requirements/{id}`.
  - [ ] `POST /api/requirements/{id}/decision` (approve, challenge or reject, reason required).
  - [ ] `GET /api/overview` (counts by status and tier, evidence quality, coverage gaps).
  - [ ] `GET /api/audit` (events by run, step or requirement).
- [ ] **10. Live Requirements, Overview and Reports views** beside the fixture views, following the
  live library's pattern, including CSV export from live data.

**Done when** the requirement produced by a run appears in the portfolio and can be approved with a
reason that shows up in the audit log.

## Phase 4: make it demoable

- [ ] **11. Host the backend**, set `VITE_LIVE_EVIDENCE=true` on Vercel with `/api` routed to it, and
  create the demo users with `python -m app.auth.manage`.
- [ ] **12. Rehearse the G60 × Europe script** twice from a clean database and fix what is slow or
  flaky.
- [ ] **13. Update the docs:** `frontend/README.md`, `architecture/09-tech-stack.md`, the status
  lines, and a decision record for phases 2 and 3.

## Only if time remains

- [ ] Delta / Tracking trigger: a re-check button that runs it against new evidence and shows the
  flags.
- [x] A PM-supplied URL as an input (`FR-IN-06`): stored as cited passages, see
  [decision 0024](decisions/0024-websites-as-sources-and-tabbed-sources-view.md).
- [ ] Pasted comments as an input (`FR-IN-07`).
- [ ] Competitor benchmarking as three steps with the tables from
  [doc 10](architecture/10-competitor-benchmarking.md).
- [ ] LangGraph with a checkpointer in place of the in-process background task.

## Cut for the demo

Weekly report scheduling, social media ingestion, web snapshots, personal-data handling, customer
feedback for China, and a measured option take rate (the labelled proxy stays).
