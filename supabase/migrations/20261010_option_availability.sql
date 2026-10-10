-- Tier 1 PDF extraction: equipment options with per-variant availability and price.

alter table public.option add column if not exists description text;
alter table public.option add column if not exists section text;
alter table public.option add column if not exists page integer;
alter table public.option drop constraint if exists option_source_id_code_market_key;
alter table public.option add constraint option_source_code_page_key unique (source_id, code, page);

create table public.option_availability (
  id uuid primary key default gen_random_uuid(),
  option_id uuid not null references public.option(id) on delete cascade,
  entry_no integer not null,            -- one option can have several price lines
  variant text not null,                -- e.g. 520d xDrive, i5 M60 xDrive
  status text not null check (status in ('standard','optional')),
  price_gross numeric,                  -- EUR incl. VAT; null = no surcharge / standard
  price_net numeric,
  condition text,                       -- e.g. 'In Verbindung mit M Sportpaket'
  inherited boolean not null default false,  -- code-only option sharing the row above
  unique (option_id, entry_no, variant)
);
create index option_availability_option_idx on public.option_availability(option_id);
create index option_availability_variant_idx on public.option_availability(variant, status);
alter table public.option_availability enable row level security;
