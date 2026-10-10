-- search_feedback: a domain filter now matches the domain and all of its child categories.
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
      and (f_domain is null or f.domain_id in (select o.id from public.ontology o where o.id = f_domain or o.parent_id = f_domain))
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

