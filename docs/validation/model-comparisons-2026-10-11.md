# Model overview validation

Date: 2026-10-11 (Europe/Berlin)

## Deployment

- Public application: https://bmw-product-intelligence.vercel.app/#models
- Local application: http://localhost:5173/#models (backend port 8000).
- Vercel deployment: `dpl_6vTqBxZzJZatJeL17yMhe4FveWZo`.
- Base commit: `2f88b149e9aad8f2aff8cb2a9bd46f9e40eae134`. This deployment includes uncommitted working-tree
  changes; it is not represented as a clean deployment of that commit.
- Artifact content SHA-256: `cbaf61d4076067448c48b09f61c207c784be60742cb447729ac93ef59ae7d76e`.
- The artifact contains the backend application and built frontend, without `.env` or BMW files.

Verified public health returns HTTP 200 with database connectivity. `/api/models` returns HTTP 401
without authentication. Production `/docs` returns HTTP 404. The served frontend model bundle
contains the median charts and per-rival crawl/reevaluation controls.

## Data and source verification

The Supabase registry covers all four dataset families and all twenty registered variants. Internal
catalog values are parsed locally; internal passages are not sent for AI specification extraction.
The comparison migration was dry-run and applied using the database skill. All four comparison
tables have RLS enabled and no public policies. Formal Supabase advisor tools were unavailable.

A current official Audi A3 technical PDF was fetched, quoted observations were validated and saved,
and the per-rival recrawl path was exercised against the same source. A new crawl timestamp and
evaluation timestamp appeared while the previous values/citations remained available. These are
actual stored public observations, not browser fixtures.

Coverage remains partial. Several discovered OEM URLs blocked scraping or returned no exact-variant
quotation. The app exposes these failures and excludes unconfirmed or incompatible measurements
from median/mean calculations. A competitor can be supplied manually with an exact variant and an
official technical page/PDF, then crawled and reevaluated inside the app. Family-level study ratings
and feedback counts are not represented as variant measurements or competitor quality scores.

## Checks

- Production frontend build passes.
- 48 desktop/mobile browser checks pass, including WCAG scans, numerical charts, feature matrix,
  per-finding source validation, crawl timestamps, empty-rival crawling, and model chat binding.
- 23 comparison checks pass, including all dataset overviews and variants, medians, interval
  aggregation, incompatible values, exact-variant quotes and cohort-scoped rival crawling.
- The final full backend regression run passes: 332 checks. Four prior tests were scoped to
  their own rolled-back records so existing sessions, conversations and tracked requirements do
  not affect their assertions.
- The documented database/embedding readiness check returns READY.
- Frontend lint exits successfully with existing warnings and the model page's asynchronous
  loading-state effect warning. These are warnings, not a clean-warning claim.
- Browser sessions/API responses are isolated test fixtures. No temporary production session was
  minted. A signed-in production chat end-to-end run was not performed.

## Repository and mirror

At the deployment verification above, these changes were still in the working tree and had not
been pushed. The documentation mirror had not yet been synced for this feature. Supabase schema
and collected source data were already applied; that is separate from documentation mirroring.
Subsequent publication uses a single squashed feature commit and a pull request into the latest
main; post-push mirror synchronization records the published commit.

## Integration with updated main

Pulled main through `68f4055`, including readable agent answers and the orchestrator's own final
reply. Model-overview chats pass their frozen comparison packet to that new final-answer call.
Renumbered the incoming final-answer decision from 0023 to 0026 because 0023 already identified
file uploads; all 26 decision IDs are unique for the Supabase mirror.

After integration, the complete backend suite passes 335 checks, and the desktop/mobile browser
suite passes 52 checks, including the new readability coverage and accessibility scans. Browser
audits wait for finite entrance animations to finish before measuring text contrast. The production
frontend build passes and lint exits successfully with warnings. Git's whitespace/conflict checks
and the scan for configured credentials pass. Supabase readiness returns READY.

The first Git-backed preview failed because the existing Vercel Vite setting ran npm at the
repository root, which has no package.json. Decision 0027 adds a root FastAPI entrypoint and a
build that installs/builds frontend/ and prepares public/ for the CDN. The new root build and
entrypoint import checks pass locally; hosted status is validated on the pull request before merge.
The deployment adapter explicitly registers the generated frontend for CDN promotion, while
hash navigation avoids an HTML fallback that could hide missing-file or disabled-doc errors.
Three additional deployment checks verify frontend delivery, API authentication priority and 404s,
including a function bundle without its CDN-promoted static directory.

Rebased the feature onto main at `b68fda8` before merging, preserving the newer answer prompt
and single-chip citation changes. The original Git preview revealed that unmatched requests
failed when its static directory was absent; the deployment adapter now checks that directory
only on frontend fallback routes.
