-- Raw Excel data: feedback comments, sales volumes, customer-study results.
-- Every row keeps its source file, sheet and row/cell so it can be cited.

create table public.feedback_raw (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  sheet text not null,
  row_no integer not null,
  ext_id text not null,                 -- e.g. G60-0001
  feedback_source text,                 -- anonymised Source A / B / C
  brand text,
  sales_description text,
  country text,
  derivate text,                        -- e-code, e.g. G60
  engine_type text,
  feedback_type text,
  comment text,
  vfc_label text,                       -- "Vfc level2 3 Name"
  vfc_level2 text,
  vfc_level3 text,
  embedding extensions.vector(1536),
  created_at timestamptz not null default now(),
  unique (source_id, row_no)
);
create index feedback_raw_source_idx on public.feedback_raw(source_id);
create index feedback_raw_filter_idx on public.feedback_raw(derivate, country, engine_type, feedback_type);
create index feedback_raw_vfc2_idx on public.feedback_raw(vfc_level2);
create index feedback_raw_embedding_idx on public.feedback_raw using hnsw (embedding extensions.vector_cosine_ops);

create table public.sales_volume (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  sheet text not null,                  -- F70 | G60_G68 | G70
  row_no integer not null,
  market text not null,
  market_code text not null,
  year integer not null,
  volume integer not null,
  is_forecast boolean not null,
  unique (source_id, sheet, market_code, year)
);

create table public.study_response (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  sheet text not null,
  cell_ref text not null,               -- e.g. B4
  market text not null,                 -- China | EU | US
  model text not null,                  -- e.g. BMW 5 Series G60
  question text not null,
  metric text not null check (metric in ('mean','share')),
  answer_option text,                   -- for shares: I Hate It ... I Love It
  value numeric not null,
  unique (source_id, sheet, cell_ref)
);
create index study_response_q_idx on public.study_response(question, model, market);

-- semantic search over feedback comments, with the usual filters
create or replace function public.match_feedback(
  query_embedding extensions.vector(1536),
  match_count integer default 10,
  filter_derivate text default null,
  filter_country text default null
)
returns table (
  id uuid, file text, sheet text, row_no integer, ext_id text, country text, engine_type text,
  feedback_type text, comment text, vfc_level2 text, vfc_level3 text, similarity double precision
)
language sql stable
set search_path = public, extensions
as $$
  select f.id, s.uri, f.sheet, f.row_no, f.ext_id, f.country, f.engine_type,
         f.feedback_type, f.comment, f.vfc_level2, f.vfc_level3,
         1 - (f.embedding <=> query_embedding)
  from public.feedback_raw f join public.source s on s.id = f.source_id
  where f.embedding is not null
    and (filter_derivate is null or f.derivate = filter_derivate)
    and (filter_country is null or f.country = filter_country)
  order by f.embedding <=> query_embedding
  limit match_count;
$$;

alter table public.feedback_raw enable row level security;
alter table public.sales_volume enable row level security;
alter table public.study_response enable row level security;
