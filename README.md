# attention_is_all_we_have

BMW "AI for Product Decision Making" hackathon — a multi-agent system that turns customer
feedback, product data, sales data, and web research into cited, PM-approved vehicle requirements.

Software idea: [`docs/idea.md`](docs/idea.md). Architecture docs: [`docs/README.md`](docs/README.md).
Agent/push rules: [`AGENTS.md`](AGENTS.md).

## Setup

- Put the provided BMW files in `data/` (gitignored).
- `.env` (gitignored): `OPENAI_API_KEY`, `SUPABASE_DB_URL` (direct connection string).
- `pip install -r ingest/requirements.txt`; PDFs also need `pdftotext`/`pdfinfo` (poppler).
- Schema: `supabase/migrations/` (applied to the Supabase project).

## Load and query

```
python ingest/load_pdfs.py                  # chunk + embed the catalog PDFs
python ingest/load_excel.py                 # feedback, sales, customer studies
python ingest/load_options.py               # equipment options with per-variant availability
python ingest/seed_ontology.py              # domains, vehicle lines, markets, category labels
python ingest/ask_pdf.py "Welche Felgen gibt es für den 5er?" --line G60
```

## Market & Trend Agent

The first agent implementation is the Market & Trend Agent. It turns cited web research into
`market_trend` findings, keeps URL + retrieval date locators, stores web source trust tiers, and
leaves the step in `awaiting_review` for PM acceptance.

```
python agents/market_trend_agent.py "What comfort trends matter for premium sedans?" --vehicle-line G60 --market US --dry-run
python agents/market_trend_agent.py "What comfort trends matter for premium sedans?" --vehicle-line G60 --market US --run-id <uuid>
```

For deterministic demos or tests, pass `--seed-sources path/to/sources.json` with a JSON list of
`url`, `title`, and `snippet` entries. To avoid OpenAI as well, pass a model-output fixture via
`--draft-json`:

```
python agents/market_trend_agent.py "comfort trends" --vehicle-line G60 --market US \
  --seed-sources tests/fixtures/market_trend_sources.json \
  --draft-json tests/fixtures/market_trend_draft.json \
  --dry-run
```

Run the local tests without external services:

```
python3 -m unittest discover -s tests
```
