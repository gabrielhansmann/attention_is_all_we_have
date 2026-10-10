-- Model overview registry, immutable source observations, explicit cohorts and frozen chat context.
create table public.comparison_model (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(name) between 2 and 160),
  origin text not null check (origin in ('dataset','manual','competitor')),
  vehicle_line text,
  identity jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (name)
);
create unique index comparison_dataset_line on public.comparison_model(vehicle_line) where origin='dataset';

create table public.comparison_research (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.comparison_model(id),
  variant text not null default '',
  market text not null,
  status text not null check (status in ('running','completed','partial','failed')),
  notes jsonb not null default '[]'::jsonb,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);
create index comparison_research_lookup on public.comparison_research(model_id,market,variant,started_at desc);
create unique index comparison_one_research on public.comparison_research(model_id,market,variant) where status='running';

create table public.comparison_observation (
  id uuid primary key default gen_random_uuid(),
  research_id uuid not null references public.comparison_research(id),
  model_id uuid not null references public.comparison_model(id),
  variant text not null,
  powertrain text check (powertrain in ('ICE','PHEV','BEV')),
  market text not null,
  section text not null,
  metric text not null,
  label text not null,
  value double precision,
  upper_value double precision,
  text_value text,
  unit text not null default '',
  standard text not null default '',
  basis text not null default '',
  period text not null default '',
  direction text not null default 'neutral' check (direction in ('higher','lower','neutral')),
  chunk_id uuid not null references public.chunk(id),
  quote text not null,
  scope_quote text not null,
  extracted_at timestamptz not null default now(),
  check ((value is not null) <> (text_value is not null)),
  check (upper_value is null or (value is not null and upper_value >= value)),
  unique (research_id,model_id,variant,metric,unit,standard,basis,chunk_id)
);
create index comparison_observation_lookup on public.comparison_observation(model_id,market,variant,metric);

create table public.comparison_rival (
  id uuid primary key default gen_random_uuid(),
  model_id uuid not null references public.comparison_model(id),
  variant text not null,
  market text not null,
  rival_id uuid not null references public.comparison_model(id),
  rival_variant text not null,
  powertrain text check (powertrain in ('ICE','PHEV','BEV')),
  reason text not null,
  discovery_url text,
  selection text not null check (selection in ('automatic','manual')),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  check (model_id <> rival_id),
  unique(model_id,variant,market,rival_id)
);
create index comparison_rival_lookup on public.comparison_rival(model_id,market,variant);

alter table public.conversation add column comparison_model_id uuid references public.comparison_model(id),
  add column comparison_variant text, add column comparison_market text;
create index conversation_comparison_lookup on public.conversation(comparison_model_id,comparison_market,comparison_variant,updated_at desc);
alter table public.pipeline_run add column comparison_context jsonb;

alter table public.comparison_model enable row level security;
alter table public.comparison_research enable row level security;
alter table public.comparison_observation enable row level security;
alter table public.comparison_rival enable row level security;
