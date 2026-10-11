# 0028 — Optional-feature market impact as explicit scenarios

> Date: 2026-10-10 · Status: accepted · Builds on 0017 and 0021 · Amended by [0029](0029-automatic-market-feedback-assessment.md) for automatic directional signals

## Context

The user requested a map showing whether a chosen optional feature positively or negatively affects share in each
market. The knowledge layer contains equipment availability, feedback and sales volumes, but no validated causal
feature-to-share model or option adoption baseline. Coloring countries with inferred numeric forecasts would
misrepresent that evidence.

## Decision

Add a Market impact view to the existing authenticated frontend. Read cited optional equipment using a new protected
`GET /api/market-impact/options?line=` route over `knowledge.tools.get_options`, bounded at 200 options with an explicit
truncation flag. Allow a clearly labeled custom feature if catalog evidence is absent.

The user enters market-share changes in percentage points and optional baseline shares. Positive, negative, zero
and unassessed values have distinct map colors and text labels. Validate numbers and resulting shares; do not
silently clamp them or turn missing assumptions into zero. The inclusion switch sets the feature's effect to zero
while preserving assumptions for comparison. Isolate scenarios by feature and vehicle line, keep them in memory,
and offer a JSON export containing assumptions, calculated results, and the selected catalog citation.

Use public-domain Natural Earth country geometry, preprojected into a local asset. The map applies each business
market assumption to its whole schematic group: Europe excluding Russia (EU), China, United States, or rest of world.
Document that grouping next to the map and in the export. Keep equivalent market buttons for keyboard use and text
labels for users who cannot distinguish the colors. Keep BMW tokens, rounded shadcn controls and the current shell.

## Consequences

The map is usable without fabricating forecasts and without a map service or runtime geometry dependency. It needs
no schema migration. Catalog outages remain visible and custom scenarios remain usable. Values are not saved to the
server and leaving the view discards them unless exported. A future prediction model must define its inputs,
calibration, uncertainty and evidence before it can replace the scenario assumptions. This decision amends the
frontend boundary in `docs/architecture/12-repo-structure.md`.
