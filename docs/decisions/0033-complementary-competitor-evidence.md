# 0033: Collect complementary competitor evidence by missing section

> Date: 2026-10-11 · Status: accepted · Amends [0031](0031-recoverable-competitor-collection.md)

## Context

Collection stopped after its first validated number. A technical PDF with three accepted fields
prevented collection from a second source and prevented searches for missing fields. The metric
vocabulary omitted dimensions, weight, towing and top speed already published in technical sheets.
Wrapped rows placed their explicit units outside the extractor's selected lines. Brochure tables
in the middle were not inspected. Requiring an engine variant for family-level equipment descriptions
also discarded useful information without distinguishing its granularity.

## Decision

Discover up to four complementary official URLs per rival and keep equipment pages alongside
technical PDFs. Accumulate validated evidence across sources, deduplicate repeated passages and
skip already fetched linked PDFs. Search for missing fields, with a second pass focused on equipment.
Bound collection to six source pages and two supplemental searches per target, sharing a 250-second
request deadline within the existing 300-second Vercel function limit. Failure retains prior evidence
and reports remaining field gaps. Robots, public-address and redirect checks remain mandatory.

Automatic refresh keeps each previously selected exact variant and disabled competitor choice.
It refreshes that variant's existing source alongside new discovery URLs. An explicit manual
variant change is committed only after validated exact-variant evidence is stored; family-level
equipment alone cannot replace an existing selection. A failed fetch must not hide prior facts
by switching the cohort to an unsourced variant. Newly discovered empty candidates remain retryable.

Add source-backed top speed, body width excluding mirrors, height, driver-free unladen weight and
braked towing at a 12% gradient. Internal catalog top speed is parsed locally from the selected
variant column. Missing internal measurements stay gaps; no driver-weight subtraction or unit
conversion invents a BMW reference value. Source intervals remain intervals.

Use configurable `COMPARISON_EXTRACTION_MODEL`, default `gpt-4.1`, with strict line-span output and
up to 32 observations per extraction. For wrapped wheelbase/weight/towing rows, select the shortest
original contiguous span including its label, value and explicit unit, within two adjacent lines
and six lines total. Never borrow a unit from a neighbouring field. Validate wheelbase rather than
track width, driver-free rather than driver-inclusive weight, and the 12% rather than 8% or unbraked
towing column. All accepted text remains verbatim in one stored passage.

Only qualitative connectivity, assistance and comfort may use a verified same-page model-family
identity. They visibly say “Model-family documentation; selected-variant availability unconfirmed.”
Their citation quote and scope remain original source text. Their separate basis cannot contribute
a numerical value or mean. Every numeric observation still requires exact variant identity.

Inspect at most the first 64 and last 12 brochure pages within 25 seconds and the source deadline;
retain at most 24 whole pages ranked by
specification/equipment content, and keep their original page numbers. No schema migration or
frontend calculation change is required.

## Verification and limits

Regression fixtures cover complementary sources, missing-field searches, repeated URLs, family
scope exclusions, neighbouring-unit rejection, wrapped value columns, catalog variant columns and
technical tables in brochure middles, failed variant replacements and disabled/manual selections.
A real Audi A6 technical sheet yielded nine validated fields
instead of the prior three, preserving the original quotes. The protected comparison pipeline's
reevaluation persisted those nine fields in Supabase with citations and original crawl timestamps.
This is one source validation, not a
promise of complete competitor coverage. Unavailable pages, unconfirmed standards and ambiguous
hybrid output remain visible gaps. Wider collection and the stronger extractor can cost more and
use more of the bounded request time.
