# Prioritization

> Status: `building` · Last updated: 2026-10-10 (scoring implementation and local Decision Lab; see [decision 0020](../decisions/0020-decision-lab-scenario-previews.md))

A composite score the PM can see decomposed, re-weight, and override — never a black-box rank. It
balances what BMW's own slide calls "Customer" against "Business," plus the brief's allowance for
a rough cost/effort factor.

```
score = w_c · customer_relevance + w_b · business_signal + w_s · strategic_fit − w_e · effort_proxy
```

Default weights (PM-editable per program): `w_c = 0.40`, `w_b = 0.25`, `w_s = 0.15`, `w_e = 0.20`.
Not tuned to any real dataset — a defensible starting point, nothing more.

| Component | Derived from |
|---|---|
| `customer_relevance` | Finding prevalence normalized by sample size, sentiment severity, cross-source corroboration count, market-weighted when several markets are in scope |
| `business_signal` | Uptake % of the related option in `sales_volumes.xlsx`, plus competitor-coverage gap from the Competitor Agent. A sellability proxy, not a cost model — pricing/business-case math is out of scope |
| `strategic_fit` | Continuity with the previous-generation baseline (Baseline Agent) and the PM's stated themes for this program |
| `effort_proxy` | Coarse Low/Med/High heuristic (new hardware > software/UX change). Deliberately rough, always PM-editable |
| `confidence` | Evidence-level mix + source independence count. Shown as a **separate badge**, never folded silently into rank, so "high potential, thin evidence" stays visually distinct from "confidently low priority" |

Every stored `Score` keeps the weight vector used, each raw component value, who/what computed it,
a timestamp, and a one-line generated rationale — see
[`04-data-model.md`](04-data-model.md#score) — and is versioned, so re-scoring after new evidence
never erases what a priority call used to look like.

## Implementation

[`backend/app/agents/prioritization_agent.py`](../../backend/app/agents/prioritization_agent.py) computes the
formula in code, with no model. The sub-weights that turn findings into each component are constants at the top
of the module and are a starting point like the weights above. Effort maps to low 0.05, medium 0.50, high 0.95.
A missing input counts as zero, lowers confidence by 0.10 and is listed on the score. The provided data has no
option take rate, so `business_signal` uses the share of variants where the option is standard, flagged as a
proxy. The tier is proposed on the score and never written to the requirement.

## Decision Lab (local demo)

The frontend's **Decision Lab** lets the PM preview alternative priorities before saving them.
Four illustrative lenses (Customer first, Growth focused, Strategic fit, Delivery first) and
four sliders use the same signed composite formula as the local requirement portfolio. Local
component scores and weights use 0–100 values, so the sum is divided by 10000. Effort is
subtracted; negative scores are preserved. Confidence is always separate.

Moving a slider redistributes the other weights proportionally and assigns rounding residue
deterministically, keeping integer weights at 100%. The ranked comparison shows saved and
scenario scores, rank movement, shortlist entries and exits, confidence, source links, and
the component calculation. The shortlist includes the selected scope's top 1–5 non-rejected
requirements. Challenged requirements remain visible for review; ties use requirement ID.
Membership across the four example lenses describes sensitivity to weights, never evidence
quality, a probability, or an engineering feasibility result.

Exploration changes no persisted weights or requirement evidence. **Apply scenario weights**
requires a reason, records the old and new vectors and shortlist changes in browser decision
history, and recalculates all local demo requirements. Weights remain workspace-wide, while
the ranking preview is scoped by vehicle line and market. Changing scope resets the preview
to saved weights. A Markdown brief exports the comparison, cited source locators, source
excerpts, acceptance criteria, and assumptions for shortlisted and departing requirements.

This is explicitly illustrative browser data, not the backend's versioned `Score` records.
The lab makes no API calls, launches no agents, and does not save server decisions. A live
version requires backend requirements, scoring, and audit endpoints before it can make
programme commitments.

## Worked example

`R-2031` — *Fast-response seat ventilation*, built around BMW's own slide example.

- **Score:** 0.49 / 1.00 → Tier 2 (should-have). Tiers: ≥0.65 must-have, 0.40–0.65 should-have,
  <0.40 watch-list.
- **customer_relevance 0.78** — two independent BMW-internal findings (a verbatim complaint and a
  customer-study item scored 2.9/5, n=340, EU) corroborate a comfort gap.
- **business_signal 0.41** — moderate option-uptake signal; one competitor review notes a faster
  rival response time (review-estimated, not lab-verified — flagged as an assumption).
- **strategic_fit 0.60** — aligns with the program's stated comfort-parity theme.
- **effort_proxy low** — software/calibration change, not new hardware.
- **confidence 0.65** — moderate; EU-only sample so far, no lab-verified benchmark yet.

Rationale (agent-generated): *"Two independent BMW-internal sources plus one competitor review
corroborate a comfort gap; moderate business signal from option uptake; low estimated effort —
lands mid-tier pending a lab-verified response-time benchmark."*

Full linked findings, assumptions, and its audit trail are in
[`07-audit-trail.md`](07-audit-trail.md#worked-example-r-2031).
