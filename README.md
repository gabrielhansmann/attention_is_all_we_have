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
python ingest/ask_pdf.py "Welche Felgen gibt es für den 5er?" --line G60
```
