-- Web research metadata and citable snapshots for agent-produced findings.

alter table public.source add column if not exists input_family text
  check (input_family in ('feedback','website','social_media','internal_data'));
alter table public.source add column if not exists channel text;
alter table public.source add column if not exists origin text
  check (origin in ('uploaded','pasted','pm_supplied_link','agent_search','connector'));
alter table public.source add column if not exists language text;
alter table public.source add column if not exists added_by text;
alter table public.source add column if not exists ingest_status text
  check (ingest_status in ('pending','succeeded','failed'));
alter table public.source add column if not exists ingest_report jsonb not null default '{}'::jsonb;

alter table public.finding add column if not exists source_snapshot text;
alter table public.finding add column if not exists assumptions text[] not null default '{}';
alter table public.finding add column if not exists dedupe_key text;

create unique index if not exists finding_dedupe_key_idx
  on public.finding(dedupe_key)
  where dedupe_key is not null;
