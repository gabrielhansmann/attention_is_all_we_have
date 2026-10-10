# 0020 — Preview priority trade-offs in a local Decision Lab

Date: 2026-10-10 · Status: accepted

## Context

The demo portfolio already supports editable scoring weights, but a PM cannot see the
consequences of a different priority strategy before saving. The architecture requires
explainable scores and keeps confidence separate from priority. A creative project extension
should strengthen that decision workflow while respecting the demo/live boundary.

## Decision

Add Decision Lab as a sixth workspace view. Compare saved priorities with a local scenario
using four illustrative lenses and proportionally rebalanced sliders. Preserve the existing
signed composite formula and thresholds. Keep slider weights as integers totaling 100%.
Rank non-rejected requirements in the current scope and show movements across a selectable
top 1–5 shortlist. Break score ties by requirement ID. Display confidence, review status,
component contributions, and clickable source citations alongside rank changes.

Show shortlist membership across the four presets as a measure of sensitivity to weights.
Label it as illustrative and distinguish it from probability and evidence confidence.
Export a Markdown comparison with source locators, excerpts, acceptance criteria, and
assumptions for shortlisted and departing requirements.

Preview state belongs to the view and resets on scope changes or leaving the view. Saving
requires a reason and records the vectors, shortlist changes, scope, and reason in the
existing browser audit history. Saved weights continue to apply across the local demo
workspace, with that consequence stated in the view and confirmation dialog.

## Consequences

- The PM can explore a trade-off before changing saved priorities, without implying a new
  source, agent result, engineering assessment, or approved requirement.
- The lab remains usable offline with no new dependencies, API routes, database schema,
  authentication changes, or service credentials.
- Browser history is still editable local data. Server score versioning and live audit
  persistence remain prerequisites for production decisions.
- Verify normalization and exact ranking calculations, negative scores, stable ties,
  preview isolation, reason-required saving, persistence, export citations, empty states,
  keyboard controls, desktop/mobile layout, and automated accessibility.
