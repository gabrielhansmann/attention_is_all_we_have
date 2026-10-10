# 0007 — Parse equipment tables by position; seed the ontology from the feedback labels

> Date: 2026-10-10 · Status: accepted

## Context

Decision 0006 left two gaps: the catalogs' ■/□ marks could not be tied to a model variant from the
flattened text, and the ontology was empty while the feedback files carry ~220 category labels.

## Decision

1. **Equipment tables are parsed by x position** (pdfplumber), not as text. Variant columns come
   from the rotated page headers, matched to marks by x. Result: `option` +
   `option_availability` (status, gross/net price, condition, inherited flag). Verified by checking
   that every mark on the equipment pages is captured exactly once.
2. **Merge PDF chunk fragments** under 250 characters into the neighbouring chunk on the same page
   (277 → 149 chunks); text stays verbatim so citations hold.
3. **Seed the ontology** with the 8 domains from the scaling doc plus two the data forced:
   **Range & Charging** (in scope per the overview) and **Safety** (airbags, seat belts, child seats,
   stability control, tire pressure — flagged out of scope as regulatory). Vehicle lines F70/G60/G68/G70,
   markets EU/CN/US/RoW. Each `vfc_level2` label becomes a child of one domain (model classification
   with hand overrides). Keys, door access and simple controls count as Usability, collision
   warnings and cameras as Driver Assistance.

## Consequences

- "Is X standard on the 530e?" is now a SQL query, not a guess from text.
- Pages without SA-code columns (selected standard equipment, package descriptions, technical
  values) are not in the option tables; they remain searchable chunks.
- The label → domain mapping is machine-assisted; review it before it drives scoring.

## Note: scope comes from the question, not a fixed slice

The data is uneven across lines and markets (e.g. G60 has 238 comments from European countries and
4,365 from the US; F70 is the European-heavy file). That is not a reason to narrow the system to
one slice: every vehicle line and market stays loaded, and the PM's question decides which
evidence the agents use. The uneven sample sizes are surfaced where they matter, as `sample_size`
on findings and the confidence badge on scores.
