-- Knowledge layer: normalization (step 1), evidence store (step 2), retrieval functions (step 3).
-- As applied to the project (recorded as migration 20261010154426 'knowledge_layer'). Heavy: one pass over
-- 13.7k feedback rows with an HNSW index; allow minutes. search_feedback's domain filter is replaced by
-- 20261011_search_feedback_domain_filter.sql.

-- Knowledge layer: normalization (step 1), evidence store (step 2), retrieval functions (step 3).
-- Backfills existing rows so every evidence table speaks the same vocabulary:
-- vehicle_line, market_code (EU/CN/US/RoW), ontology domain, polarity, powertrain.

-- ---------- 1. Normalization ----------
create table public.country_market (
  country_code text primary key,
  market_code text not null,
  country_name text not null
);
insert into public.country_market values
  ('US','US','United States'),('GB','EU','United Kingdom'),('SE','EU','Sweden'),('DK','EU','Denmark'),
  ('NO','EU','Norway'),('FR','EU','France'),('FI','EU','Finland'),('ES','EU','Spain'),('LV','EU','Latvia'),
  ('JP','RoW','Japan'),('KR','RoW','South Korea'),('CA','RoW','Canada'),('AU','RoW','Australia'),
  ('ZA','RoW','South Africa');

create table public.model_variant (
  id uuid primary key default gen_random_uuid(),
  vehicle_line text not null,
  name text not null,
  powertrain text check (powertrain in ('ICE','PHEV','BEV')),
  unique (vehicle_line, name)
);
insert into public.model_variant (vehicle_line, name)
  select distinct o.vehicle_line, a.variant from public.option o join public.option_availability a on a.option_id = o.id;
update public.model_variant set powertrain = case
  when vehicle_line = 'G60' and name like 'i5%' then 'BEV'
  when vehicle_line = 'G60' and (name like '530e%' or name like '550e%') then 'PHEV'
  when vehicle_line = 'G70' and name like 'i7%' then 'BEV'
  else 'ICE' end;
alter table public.option_availability add column variant_id uuid references public.model_variant(id);
update public.option_availability a set variant_id = v.id
  from public.option o, public.model_variant v
  where o.id = a.option_id and v.vehicle_line = o.vehicle_line and v.name = a.variant;
alter table public.option_availability alter column variant_id set not null;
create index option_availability_variant_id_idx on public.option_availability(variant_id);

alter table public.feedback_raw
  add column vehicle_line text,
  add column market_code text,
  add column domain_id uuid references public.ontology(id),
  add column polarity text check (polarity in ('positive','negative','request')),
  add column powertrain text check (powertrain in ('ICE','PHEV','BEV'));
update public.feedback_raw set vehicle_line = derivate;
update public.feedback_raw f set market_code = c.market_code from public.country_market c where c.country_code = f.country;
update public.feedback_raw f set domain_id = o.id from public.ontology o
  where o.kind = 'domain' and o.parent_id is not null and o.label = f.vfc_level2;
update public.feedback_raw set polarity = case feedback_type
  when 'Likes' then 'positive' when 'Difficult to Use' then 'negative' when 'Defect' then 'negative'
  when 'Wants' then 'request' end;
update public.feedback_raw set powertrain = case engine_type
  when 'ICE' then 'ICE' when 'PHEV' then 'PHEV' when 'BEVE' then 'BEV' end;
create index feedback_raw_norm_idx on public.feedback_raw(vehicle_line, market_code, domain_id, polarity, powertrain);

alter table public.study_response add column vehicle_line text, add column market_code text;
update public.study_response set
  vehicle_line = (regexp_match(model, '(F70|G60|G68|G70)'))[1],
  market_code = case market when 'China' then 'CN' when 'EU' then 'EU' when 'US' then 'US' end;
create index study_response_norm_idx on public.study_response(vehicle_line, market_code);

-- the G60_G68 sheet covers both lines; G68 is the Chinese 5 Series variant (assumption, see docs)
alter table public.sales_volume add column vehicle_line text;
update public.sales_volume set vehicle_line = case
  when sheet = 'G60_G68' and market_code = 'CN' then 'G68'
  when sheet = 'G60_G68' then 'G60'
  else sheet end;
create index sales_volume_norm_idx on public.sales_volume(vehicle_line, market_code, year);

-- ---------- 2. Evidence store ----------
alter table public.finding
  add column domain_id uuid references public.ontology(id),
  add column polarity text check (polarity in ('positive','negative','request'));
create index finding_domain_idx on public.finding(domain_id);

-- a finding cites one or more raw evidence rows; exactly one reference per row keeps integrity
create table public.finding_evidence (
  id uuid primary key default gen_random_uuid(),
  finding_id uuid not null references public.finding(id) on delete cascade,
  feedback_raw_id uuid references public.feedback_raw(id),
  study_response_id uuid references public.study_response(id),
  sales_volume_id uuid references public.sales_volume(id),
  option_id uuid references public.option(id),
  chunk_id uuid references public.chunk(id),
  quote text,
  created_at timestamptz not null default now(),
  check (num_nonnulls(feedback_raw_id, study_response_id, sales_volume_id, option_id, chunk_id) = 1)
);
create index finding_evidence_finding_idx on public.finding_evidence(finding_id);
create index finding_evidence_feedback_idx on public.finding_evidence(feedback_raw_id);
create index finding_evidence_study_idx on public.finding_evidence(study_response_id);
create index finding_evidence_sales_idx on public.finding_evidence(sales_volume_id);
create index finding_evidence_option_idx on public.finding_evidence(option_id);
create index finding_evidence_chunk_idx on public.finding_evidence(chunk_id);

-- one citable view over every raw evidence kind: what an agent may cite, and how it reads
create view public.evidence_item with (security_invoker = true) as
  select 'feedback'::text as kind, f.id, f.vehicle_line, f.market_code, f.domain_id, f.polarity,
         s.uri as file, ('sheet ' || f.sheet || ', row ' || f.row_no || ' (' || f.ext_id || ')') as locator,
         f.comment as text
    from public.feedback_raw f join public.source s on s.id = f.source_id
  union all
  select 'pdf_text', c.id, s.vehicle_line, null, null, null, s.uri, ('page ' || c.page), c.content
    from public.chunk c join public.source s on s.id = c.source_id
  union all
  select 'option', o.id, o.vehicle_line, null, null, null, s.uri, ('page ' || o.page || ', SA ' || o.code),
         o.name || coalesce(' — ' || o.description, '')
    from public.option o join public.source s on s.id = o.source_id
  union all
  select 'study', r.id, r.vehicle_line, r.market_code, null, null, s.uri, ('sheet ' || r.sheet || ', cell ' || r.cell_ref),
         r.question || ' | ' || r.model || ' | ' || coalesce(r.answer_option || ' ', '') || r.metric || ' = ' || r.value
    from public.study_response r join public.source s on s.id = r.source_id
  union all
  select 'sales', v.id, v.vehicle_line, v.market_code, null, null, s.uri, ('sheet ' || v.sheet || ', row ' || v.row_no),
         v.vehicle_line || ' ' || v.market || ' ' || v.year || ': ' || v.volume || ' units' ||
         case when v.is_forecast then ' (forecast)' else '' end
    from public.sales_volume v join public.source s on s.id = v.source_id;

-- ---------- 3. Retrieval: hybrid (vector + keyword, reciprocal-rank fusion) ----------
alter table public.feedback_raw
  add column fts tsvector generated always as (to_tsvector('english', coalesce(comment, ''))) stored;
create index feedback_raw_fts_idx on public.feedback_raw using gin (fts);
alter table public.chunk
  add column fts tsvector generated always as (to_tsvector('german', coalesce(heading, '') || ' ' || content)) stored;
create index chunk_fts_idx on public.chunk using gin (fts);

create or replace function public.search_feedback(
  query_embedding extensions.vector(1536),
  query_text text default null,
  match_count integer default 10,
  f_line text default null, f_market text default null, f_domain uuid default null,
  f_polarity text default null, f_powertrain text default null
)
returns table (
  id uuid, file text, sheet text, row_no integer, ext_id text, vehicle_line text, market_code text,
  country text, powertrain text, feedback_type text, polarity text, domain text, comment text,
  similarity double precision, score double precision
)
language sql stable
set search_path = public, extensions
as $$
  with base as (
    select f.* from public.feedback_raw f
    where (f_line is null or f.vehicle_line = f_line)
      and (f_market is null or f.market_code = f_market)
      and (f_domain is null or f.domain_id = f_domain)
      and (f_polarity is null or f.polarity = f_polarity)
      and (f_powertrain is null or f.powertrain = f_powertrain)
  ),
  vec as (
    select id, row_number() over (order by embedding <=> query_embedding) as r
    from base where embedding is not null order by embedding <=> query_embedding limit 50
  ),
  kw as (
    select b.id, row_number() over (order by ts_rank_cd(b.fts, q) desc) as r
    from base b, websearch_to_tsquery('english', query_text) q
    where query_text is not null and b.fts @@ q order by ts_rank_cd(b.fts, q) desc limit 50
  ),
  fused as (
    select id, sum(1.0 / (60 + r)) as score from (select * from vec union all select * from kw) u group by id
  )
  select f.id, s.uri, f.sheet, f.row_no, f.ext_id, f.vehicle_line, f.market_code, f.country, f.powertrain,
         f.feedback_type, f.polarity, o.label, f.comment, 1 - (f.embedding <=> query_embedding), fu.score
  from fused fu
  join public.feedback_raw f on f.id = fu.id
  join public.source s on s.id = f.source_id
  left join public.ontology o on o.id = f.domain_id
  order by fu.score desc limit match_count;
$$;

create or replace function public.search_docs(
  query_embedding extensions.vector(1536),
  query_text text default null,
  match_count integer default 8,
  f_line text default null
)
returns table (
  id uuid, file text, title text, vehicle_line text, page integer, heading text, content text,
  similarity double precision, score double precision
)
language sql stable
set search_path = public, extensions
as $$
  with base as (
    select c.* from public.chunk c join public.source s on s.id = c.source_id
    where c.embedding is not null and (f_line is null or s.vehicle_line = f_line)
  ),
  vec as (
    select id, row_number() over (order by embedding <=> query_embedding) as r
    from base order by embedding <=> query_embedding limit 30
  ),
  kw as (
    select b.id, row_number() over (order by ts_rank_cd(b.fts, q) desc) as r
    from base b, websearch_to_tsquery('german', query_text) q
    where query_text is not null and b.fts @@ q order by ts_rank_cd(b.fts, q) desc limit 30
  ),
  fused as (
    select id, sum(1.0 / (60 + r)) as score from (select * from vec union all select * from kw) u group by id
  )
  select c.id, s.uri, s.title, s.vehicle_line, c.page, c.heading, c.content,
         1 - (c.embedding <=> query_embedding), fu.score
  from fused fu join public.chunk c on c.id = fu.id join public.source s on s.id = c.source_id
  order by fu.score desc limit match_count;
$$;

alter table public.country_market enable row level security;
alter table public.model_variant enable row level security;
alter table public.finding_evidence enable row level security;
