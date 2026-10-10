# 0021 — Chat-first frontend with rounded components and soft elevation

> Date: 2026-10-10 · Status: accepted · Amends the shape and elevation rules of [`design.md`](../../design.md) and [`ui-design-guidelines.md`](../ui-design-guidelines.md); builds on [0017](0017-minimal-live-only-frontend.md)

## Context

The frontend looked like a plain document site: a top bar, a text-only conversation list beside the thread, and
rectangular, hairline-bordered components. The product is a research conversation, so it should read like a modern
chat app. The user asked explicitly for rounded edges, icons, and chat history on the left.

## Decision

1. **Layout.** A left sidebar (fixed on desktop, a sheet below `md`) holds the brand, New chat, the three views, the
   chat history grouped by recency, the account menu and the backend status. The Research view is a centred thread with
   a rounded composer, an empty state with example questions, and a typing indicator while an agent works.
2. **Shape.** `--radius` is 0.75rem. Cards, inputs, buttons and menus are rounded; chips and avatars are pills.
   This overrides the "rectangular components" default in `design.md`.
3. **Elevation.** Three soft shadow tokens (`xs`, `sm`, `md`) replace "no drop shadows"; they are used only on the composer,
   cards and the sign-in panel. Depth otherwise still comes from surface contrast (`canvas-tint` behind white cards).
4. **Unchanged brand rules.** BMW Blue stays the only action colour, white canvas, Inter as the substitute typeface, light
   theme only, no gradients or glows. Body weight is now 400 and headings 600 (was 300 and 700) for legibility in dense chat text.
5. **One icon family** (lucide, already in the project) and shadcn components on Base UI (`avatar`, `dropdown-menu`,
   `scroll-area`, `sheet`, `tooltip`).

## Consequences

Brand fidelity to BMW's corporate site is looser on purpose; the product is an internal tool, not a marketing page.
Tests that reach the sidebar open the sheet first on small screens (`openMenu` and `closeMenu` in `tests/helpers.ts`).
