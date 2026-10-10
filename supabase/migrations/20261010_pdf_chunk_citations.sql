-- Citable PDF chunks: page + position per chunk, source title, and a cosine search function.

alter table public.source add column if not exists title text;

alter table public.chunk add column if not exists page integer;
alter table public.chunk add column if not exists chunk_index integer;
alter table public.chunk add constraint chunk_source_page_idx_key unique (source_id, page, chunk_index);

create or replace function public.match_chunks(
  query_embedding extensions.vector(1536),
  match_count integer default 8,
  filter_vehicle_line text default null
)
returns table (
  chunk_id uuid, source_id uuid, file text, title text, vehicle_line text,
  page integer, locator text, heading text, content text, similarity double precision
)
language sql stable
set search_path = public, extensions
as $$
  select c.id, c.source_id, s.uri, s.title, s.vehicle_line,
         c.page, c.locator, c.heading, c.content,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.chunk c
  join public.source s on s.id = c.source_id
  where c.embedding is not null
    and (filter_vehicle_line is null or s.vehicle_line = filter_vehicle_line)
  order by c.embedding <=> query_embedding
  limit match_count;
$$;
