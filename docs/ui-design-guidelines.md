# UI design guidelines

Project-specific adaptation of the supplied `design-taste-frontend` guidance.
Read alongside [`../design.md`](../design.md), which defines the BMW design system.

## Scope and precedence

Use BMW tokens for every generated UI. Apply the marketing-page guidance below to landing
pages, portfolios, editorial pages, and redesigns. Do not impose marketing hero, photography,
section variety, or short-copy requirements on the requirement-evidence engine's dashboards,
data tables, agent review screens, or multi-step product workflows. Those screens need clear
information hierarchy, evidence, accessible controls, and complete interaction states.

Explicit user instructions and BMW brand rules override generic taste defaults. In particular:

- Pure white canvas, BMW Blue `#1c69d4`, dark navy hero bands, and 700/300 typography remain.
- Inter is an approved substitute when licensed BMW Type Next Latin is unavailable.
- Rectangular buttons, cards, inputs, and chips are the default. No drop shadows.
- Light surfaces with dark hero or CTA bands are intentional BMW composition.
- Do not invent a dark theme unless requested; the supplied brand system defines a light base.
- M stripes belong only in M-model or motorsport contexts.

## Before implementation

1. Infer page kind, audience, existing brand, assets, and accessibility constraints.
2. State: "Reading this as: <page kind> for <audience>, with a <vibe> language,
   leaning toward <design system or aesthetic family>."
3. Set `DESIGN_VARIANCE`, `MOTION_INTENSITY`, and `VISUAL_DENSITY` explicitly.
   For measured BMW corporate marketing, start at 4 / 3 / 4; adapt to the brief.
4. For redesigns, audit tokens, information architecture, content, interactions, accessibility,
   analytics, and SEO before editing. Preserve routes, nav labels, form names/order, brand marks,
   and legal/consent copy unless the user authorizes changes.
5. For a specific visual reference, record concrete ratios, spacing, colors, radii, shadows,
   icon treatment, layout structure, and deliberate omissions. Mark estimates as estimates.
   Write a yes/no check for each rule and verify the composition can be rebuilt from the rules.
6. Inspect the existing stack and `package.json` before importing dependencies. Reuse the
   project's foundation; do not mix component systems or recreate an explicitly requested
   official design system by hand.

## Composition and copy

- Use the BMW spacing scale, 80px major section rhythm, 24px card padding, and 1440px container.
- Prefer purposeful alignment and real content hierarchy over decorative asymmetry.
- Marketing heroes: at most two desktop headline lines, 20 words of supporting copy,
  one primary and at most one secondary CTA. Keep CTAs visible in the initial viewport.
  Limit desktop top padding to 96px and hero text to four elements total.
- Keep desktop navigation on one line and 64px tall, with an 80px maximum.
- Use at most one section eyebrow per three marketing sections. Avoid numbered sections,
  scroll cues, version stamps, decorative status dots, atmospheric locale strips, and
  decoration text at the hero's bottom.
- Avoid repeated generic feature-card rows, empty bento cells, and three consecutive
  alternating image/text splits. Choose layouts that fit the actual content.
- Put supporting paragraphs directly below headings; avoid floating corner explainers.
- Keep marketing paragraphs short and quotes within three lines. Use disclosures, grouped
  content, or separate pages for long lists rather than dumping data into landing pages.
- Use plain, grammatical copy. Avoid forced metaphors, filler verbs, invented testimonials,
  fabricated metrics, and fake precision. Label sample data explicitly.
- Use one label per CTA intent and one verb per action throughout the product.
- Generated visible UI copy uses regular hyphens, commas, periods, or parentheses instead
  of em-dashes or en-dash separators. Preserve supplied source material as supplied.

## Assets and styling

- Use real brand assets and real component previews. Never fabricate screenshot-like
  rectangles, terminal windows, or dashboards as decorative product previews.
- For marketing surfaces needing photography, prefer suitable generated assets when tools
  are available, then verified real imagery. If assets cannot be obtained, use clearly marked
  placeholders and report the missing placements. Product workflows do not need stock imagery.
- Use real logos for genuine social proof; do not invent customers or decorative photo credits.
- Keep images free of decorative pills and labels. Reserve dimensions to prevent layout shifts.
- Use one icon family. Prefer Phosphor, HugeIcons, Radix, or Tabler; retain Lucide if already
  used by the project. Do not hand-draw SVG icon paths.
- Avoid gradient text, glows, glass panels, random accent colors, custom cursors, and ornamental
  grid lines. BMW photography and surface contrast provide depth.
- Self-host fonts with `font-display: swap`, or use `next/font` in Next.js.

## Interaction and engineering

- Provide meaningful loading, empty, error, disabled, selected, focus, and success states
  where the interaction requires them. Use layout-matched skeletons for loading.
- Put labels above form inputs, helper text alongside the field, and inline errors below.
  Placeholders are never labels. Ensure keyboard operation and visible focus.
- Check text, placeholders, focus indicators, and controls for WCAG AA contrast. Keep CTA
  labels on one desktop line and touch targets at least 48px where BMW specifies them.
- Use CSS Grid for grids and declare each multi-column layout's mobile collapse explicitly.
  Use `min-height: 100dvh` when a full-height layout is needed, rather than fixed `100vh`.
- Keep state local unless shared state is necessary. Put providers and interactive islands
  in Client Components in Next.js; static layouts can remain Server Components.
- Animate only when motion explains hierarchy, feedback, storytelling, or state changes.
  Honor reduced motion. Do not claim motion that has not been implemented.
- Use Motion values for continuous pointer/scroll values, never React state. Avoid raw scroll
  listeners. Use IntersectionObserver, CSS scroll animations, Motion, or GSAP ScrollTrigger.
- Isolate animation code in client leaves and clean up effects. Do not let animation libraries
  compete over the same elements. Keep marquees to at most one per marketing page.
- For actual GSAP pinned stacks or horizontal pans, pin at `start: "top top"` and use correct
  end distances and scrub behavior. Do not add scroll hijacks merely for decoration.
- Keep z-index layers intentional, lazy-load heavy below-the-fold code, and avoid grain filters
  on scrolling containers. Target LCP < 2.5s, INP < 200ms, and CLS < 0.1.

## Pre-flight before delivery

Check applicable rules; mark out-of-scope items as such rather than inventing content to satisfy
them. Fix failures before delivering and report any checks that could not be run.

- Brief, mode, dials, reference rules, and BMW precedence are explicit.
- Colors, fonts, radii, spacing, and component states match `design.md`.
- Visible copy is grammatical, consistent, and free of decorative dash separators or fake data.
- Navigation, hero, CTAs, grids, and images fit desktop and mobile without overflow or clipping.
- Section layouts and eyebrow counts fit the marketing composition, with no empty filler cells.
- Assets load, previews are real, and social proof has a factual basis.
- Buttons, inputs, text, focus states, keyboard paths, and touch targets pass accessibility checks.
- Loading, empty, error, and disabled states work for relevant interactions.
- Motion is motivated, implemented, cleaned up, and disabled or simplified under reduced motion.
- Test every supported theme; do not require an invented theme merely to satisfy a generic rule.
- Run appropriate build checks and inspect the UI at desktop and mobile sizes. For marketing
  pages, run Lighthouse when a runnable browser environment is available; report measured
  results honestly instead of asserting Core Web Vitals from code inspection alone.
