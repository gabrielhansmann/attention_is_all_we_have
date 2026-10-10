# 0023 - Use database evidence throughout the PM workspace

> Date: 2026-10-10 · Status: accepted

## Context

This records the reviewed workspace branch based on `b696ed5`. The independently merged main-branch
changes in decisions 0017–0021 are not integrated here; those decision numbers are reserved.

The PM asked to remove hardcoded business values and use data from the database and web research.
The old portfolio, targets, scores, trends, source excerpts, research walkthrough and decision history
were generated in the browser. Real evidence and the agent runner existed beside that workspace.
The database has loaded feedback, catalogs, equipment, studies and sales, but currently no backlog
requirements or score records. Generating replacements would misrepresent missing data as evidence.

## Decision

- Remove runtime fixtures, the fixed three-step walkthrough, offline/live switches, local business-data
  persistence, synthetic target/trend displays and browser-only document registration/scoring controls.
  Test fixtures remain isolated in test directories and are not product data.
- Require backend sign-in for every view. The browser calls `/api` only, in development and production.
  Static hosting needs a same-origin API proxy; there is no environment flag enabling a fixture fallback.
- Read vehicle-line and market labels from active ontology rows. Start with all scopes selected and
  validate workspace filters against the database. Existing evidence API/planner code allowlists remain
  protocol/configuration rules, not generated business records.
- Add `GET /api/workspace/config` and scoped `GET /api/workspace`. Overview and Reports read actual
  evidence counts, recorded sales/forecasts, extracted catalog/study rows, accepted step contributions
  and audit events. Requirements reads backlog rows, their latest persisted scores and finding citations.
  Preserve null values and real zeroes. Do not infer confidence, option uptake, respondent counts,
  targets, comparison metrics or a priority tier from missing records.
- Keep accepted step contributions separate from backlog rows. This exposes actual stored web research
  and agent results without silently publishing accepted drafts/scores into different tables. Contributions
  retain their run status, including partial accepted work in an aborted run, and link to their conversation.
- Persist requirement status reviews through `PATCH /api/requirements/{id}/status`. Require the expected
  prior status and a reason, lock the row and write the status plus signed-in audit identity in one
  transaction. Reject stale or unsupported transitions. Content editing/versioning remains future work.
- Show coverage using the newest recorded non-forecast sales year from the database. Show exact feedback
  counts and missing rows instead of an arbitrary frontend thin-evidence threshold or fixed-year claim.
  Source listings include finding counts and identify stored web sources.
- Keep database queries in `app.knowledge.workspace`; route schemas live in `app.api.schemas` and are
  mirrored in frontend types. The snapshot includes bounded catalog/study/run/result/history previews;
  displayed counts state the full scope. Catalog/study tables state their preview sizes; result and
  history sections read the most recent stored contributions/events.

## Consequences

This supersedes the local fixture delivery in decision 0011 and the parallel demo/live boundary retained
in 0013 and 0022. BMW tokens, navigation and the existing authenticated runner remain. Empty stores show
empty states; outages show errors. Old local demo storage is ignored and never imported as evidence.
No migration, seeding, account creation, schema change or production deployment is needed for this change.
The optional web finding snapshot column is read when present; existing finding text remains available on
older schemas.

Automatic accepted-result publication, successor target storage, persisted scoring-weight configuration,
PM input ingestion, durable execution recovery and scheduled reports remain planned. Provider-backed
recommendation quality and full-page crawler coverage are not implied by a successful UI test.

## Validation

Database integration tests cover dynamic ontology labels, scope isolation, missing versus zero scores,
stored web citations, reason-required atomic reviews, stale-edit rejection and accepted-only results.
Coverage tests prove that a newer forecast cannot replace the latest recorded sales year. Browser tests
cover authentication, real-response rendering, missing/error states, reviews, cited exports, agent controls
and desktop/mobile accessibility. Backend and frontend production checks are run alongside these tests.

Verified: 273 backend tests passed; final schema/authentication checks passed all 44 targeted tests.
All 36 desktop/mobile browser tests passed. The production build and lint passed without warnings.
Read-only checks against the actual database confirmed the workspace responses, and real-response
desktop/mobile screenshots had no page overflow. All relative links resolve across 48 Markdown files;
removed fixture content and the old business-storage key are absent from the production bundle.
