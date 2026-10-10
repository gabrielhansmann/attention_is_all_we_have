# attention_is_all_we_have

BMW "AI for Product Decision Making" hackathon — a multi-agent system that turns customer
feedback, product data, sales data, and web research into cited, PM-approved vehicle requirements.

Software idea: [`docs/idea.md`](docs/idea.md). Architecture docs: [`docs/README.md`](docs/README.md).
Agent/push rules: [`AGENTS.md`](AGENTS.md). Repo layout: [`docs/architecture/12-repo-structure.md`](docs/architecture/12-repo-structure.md).

## Layout

```
backend/     FastAPI app, agents, knowledge layer, ingestion, orchestration (Python package `app`)
frontend/    Vite + React + TypeScript + Tailwind + shadcn/ui (BMW design tokens)
supabase/    SQL migrations
docs/        architecture, decisions, requirements
skills/      agent skills (database setup)
data/        provided BMW files (gitignored)
```

## Frontend

The responsive PM workspace lives in [`frontend/`](frontend/README.md). It implements the
documented overview, editable successor targets, requirement reviews, guided research gates,
evidence library, and programme reports using the BMW design tokens. The current frontend uses
clearly labeled illustrative data and browser storage; it does not call the agent backend yet.

```bash
cd frontend
npm ci
npm run dev
```

See the [frontend guide](frontend/README.md) for build, browser tests, and Vercel deployment.
Live demo: [bmw-product-intelligence.vercel.app](https://bmw-product-intelligence.vercel.app).

## Setup

1. Put the provided BMW files in `data/` (gitignored) if you want to re-run the loaders. The data is already loaded in Supabase.
2. `cp .env.example .env` and fill in `OPENAI_API_KEY` and `SUPABASE_DB_URL`
   (see [`skills/database-setup/SKILL.md`](skills/database-setup/SKILL.md)).
3. `make install` (Python 3.11+, Node 24 LTS, npm). PDF loaders also need `pdftotext`/`pdfinfo` (poppler).
4. `make check-db` to verify the database connection and the OpenAI key.
5. Create your first user (the API needs sign-in): `cd backend && ../.venv/bin/python -m app.auth.manage create-user --email you@example.com --name "Your Name"`. The password is typed at a hidden prompt.

## Run

```
make dev          # backend on :8000 and frontend on :5173 (BACKEND_PORT=8001 make dev if 8000 is taken)
make backend      # API only: http://localhost:8000/api/health, interactive docs at /docs
make frontend     # UI only: http://localhost:5173 (proxies /api to the backend)
make test         # backend tests, no database or OpenAI key needed
make build        # type-check and build the frontend
```

The UI has five views: **Overview**, **Requirements**, **Research**, **Evidence library**, and
**Reports**. In local development, Evidence library also offers **Browse backend evidence** to
search stored feedback/catalog text and exact counts through `/api`. Every live result shows
its file, location, and verbatim quote. The Research flow remains a guided fixture demo.

## Load and query data

Run from any directory after `make install` (the scripts find the root `.env` and `data/` themselves):

```
python -m app.ingest.load_pdfs               # chunk + embed the catalog PDFs
python -m app.ingest.load_excel              # feedback, sales, customer studies
python -m app.ingest.load_options            # equipment options with per-variant availability
python -m app.ingest.seed_ontology           # domains, vehicle lines, markets, category labels
python -m app.knowledge.tools                # demo of the agent retrieval tools (search, lookups, counts, cite)
python -m app.ingest.ask_pdf "Welche Felgen gibt es für den 5er?" --line G60
```

Use the repo's virtualenv (`.venv/bin/python`) or activate it first.

## Market & Trend Agent

The first agent implementation is the Market & Trend Agent. It turns cited web research into
`market_trend` findings, keeps URL + retrieval date locators, stores web source trust tiers, and
leaves the step in `awaiting_review` for PM acceptance.

```
python -m app.agents.market_trend_agent "What comfort trends matter for premium sedans?" --vehicle-line G60 --market US --dry-run
python -m app.agents.market_trend_agent "What comfort trends matter for premium sedans?" --vehicle-line G60 --market US --run-id <uuid>
```

For deterministic demos or tests, pass `--seed-sources path/to/sources.json` with a JSON list of
`url`, `title`, and `snippet` entries. To avoid OpenAI as well, pass a model-output fixture via
`--draft-json`:

```
python -m app.agents.market_trend_agent "comfort trends" --vehicle-line G60 --market US \
  --seed-sources backend/tests/fixtures/market_trend_sources.json \
  --draft-json backend/tests/fixtures/market_trend_draft.json \
  --dry-run
```
