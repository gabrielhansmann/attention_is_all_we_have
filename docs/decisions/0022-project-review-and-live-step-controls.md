# 0022 — Review reasons, safe failure handling and live frontend step controls

> Date: 2026-10-10 · Status: accepted

## Context

This records the reviewed workspace branch based on `b696ed5`. The independently merged main-branch
changes in decisions 0017–0021 are not integrated here; those decision numbers are reserved.

The runner and sign-in API existed, while the live frontend still stopped at planning. Current docs
contradicted older requirements about manually launching every agent and overstated option uptake,
full-source Critic verification, backlog persistence and durable execution. Review also found that a failed
step could be accepted, reasons were optional, failed-login counters could lose concurrent updates,
and drafting retries left stale provenance links or added links to requirements the PM had already reviewed.

## Decision

1. **The live UI uses the runner.** Confirming a plan starts research. The conversation is refreshed while
   steps run; only the newest card is actionable. Accept starts the next agent; Reject requires a separate
   explicit choice to continue with a coverage gap or abort. Retry reruns the same step. Edit changes only
   its summary, without changing evidence, metrics or scores.
2. **Failed output cannot be accepted.** The backend checks the actual stored output, so editing the failure
   summary cannot disguise it. Failure and Critic metadata survive summary edits. Retry and rejection remain available.
3. **Status-changing review actions need reasons.** Accept, Retry and Reject validate at least three
   non-whitespace characters. Acceptance retains its reason on the step and in the audit event. Starting
   a run writes a `run_started` event with the signed-in PM as actor; automatic step starts remain system events.
4. **Account changes are atomic.** The admin CLI commits password/deactivation changes together with
   session revocations. Sign-in locks the account row so concurrent wrong passwords cannot lose counts.
5. **Draft provenance is replaced on retry.** The standalone drafting storage helper replaces finding and
   cluster links only after a successful insert/update of a draft. A requirement moved beyond draft is
   left untouched, including its evidence links. This does not add backlog writes to the runner.
6. **Ordinary review language is in scope.** Market/Trend no longer classifies standalone “fine” or
   “mandatory” as regulatory. Explicit regulation, compliance, fines and pricing phrases still flag it.
7. **CSS resets stay in the base layer.** Unlayered resets overrode Tailwind button colors, yielding dark
   text on BMW blue. Layering restores white primary text and borders; live buttons use BMW's 48px target
   and solid active blue rather than a translucent hover that weakens contrast.
8. **Tests isolate their data.** Browser tests mock all API traffic, and database tests inspect/update only
   their own users and conversations. Existing shared data is preserved and test transactions roll back.

9. **Input and scope integrity.** Malformed model agent lists produce a controlled planner error; invalid
   agent names are dropped safely. Source trust uses known domain roots and hostname boundaries rather than brand-name substrings. Blank searches do not reach embeddings. Changing evidence filters clears
   stale hits. Finding ids include source and market/vehicle scope so matching rows across files do not collide.

## Consequences

- This extends decisions 0013 and 0015, and the audit identity behavior of 0016. It supersedes the
  no-runner frontend boundary and optional acceptance reasons. It also resolves the stale drafting-link
  and Market/Trend word-matching issues noted in 0014.
- Live results remain step JSON, messages and audit events. They are not imported into the fixture
  Overview, Requirements or Reports, and the runner still does not write backlog tables.
- Durable recovery, scheduling, accepted-result persistence, full-page web snapshots and separate
  competitor-scoping gates remain planned. The Critic checks provenance rather than guaranteeing truth.
- Historical decision records and the pitch's labeled source snapshot remain historical; architecture
  and requirement docs describe the current boundary. No schema migration or production deployment is part of this review.
- Validation covers backend regression tests, desktop/mobile browser flows and accessibility, and the
  frontend production build. Full provider-backed recommendation quality remains unmeasured.

## Validation

- Backend suite: 260 tests passed, including database integration and the new regression checks.
- Browser suite: 46 tests passed across desktop and mobile, including live review controls and WCAG checks.
- Frontend production build and dependency checks passed. Lint completed with two existing warnings.
- Relative file and heading links resolve across 47 Markdown files; `git diff --check` passed.
- Frontend, backend and frontend `/api` proxy returned HTTP 200; backend health reported the database ready.
