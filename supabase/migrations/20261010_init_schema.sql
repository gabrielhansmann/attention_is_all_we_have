-- Initial schema: entities from docs/architecture/04-data-model.md plus docs mirror tables.
-- Embeddings: OpenAI text-embedding-3-small (1536 dims), cosine distance.

create extension if not exists vector with schema extensions;

-- ---------- Ontology (editable taxonomy; domains / markets / vehicle lines) ----------
create table public.ontology (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('domain','market','vehicle_line')),
  key text not null,
  label text not null,
  parent_id uuid references public.ontology(id),
  active boolean not null default true,
  unique (kind, key)
);

-- ---------- Source + Finding ----------
create table public.source (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('internal_pdf','internal_xlsx','web')),
  uri text not null,
  vehicle_line text,
  market text,
  trust_tier text check (trust_tier in ('oem','trade_press','forum_social')),
  retrieved_at timestamptz not null default now()
);

create table public.finding (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  locator text not null,
  text text not null,
  signal_type text not null check (signal_type in
    ('complaint','unmet_need','competitor_advantage','market_trend','praise','business_signal','strategic_continuity')),
  evidence_level text not null check (evidence_level in ('Verified','Interpreted','Unverified')),
  sentiment numeric,
  sample_size integer,
  market text,
  vehicle_line text,
  out_of_scope_reason text,           -- set when auto-routed to the regulatory/pricing bin
  extracted_by text not null,
  step_id uuid,                        -- FK added after step exists
  embedding extensions.vector(1536),
  created_at timestamptz not null default now()
);
create index finding_source_idx on public.finding(source_id);
create index finding_embedding_idx on public.finding using hnsw (embedding extensions.vector_cosine_ops);

-- Tier 2 semantic chunks (heading-aware), locator kept per chunk
create table public.chunk (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  locator text not null,
  heading text,
  content text not null,
  embedding extensions.vector(1536),
  created_at timestamptz not null default now()
);
create index chunk_source_idx on public.chunk(source_id);
create index chunk_embedding_idx on public.chunk using hnsw (embedding extensions.vector_cosine_ops);

-- Tier 1 deterministic option-list rows
create table public.option (
  id uuid primary key default gen_random_uuid(),
  source_id uuid not null references public.source(id),
  vehicle_line text not null,
  code text not null,
  name text not null,
  category text,
  market text,
  locator text not null,
  unique (source_id, code, market)
);

-- ---------- Pipeline run + steps ----------
create table public.pipeline_run (
  id uuid primary key default gen_random_uuid(),
  trigger text not null check (trigger in ('scheduled','pm_query')),
  vehicle_line text not null,
  market text not null,
  query_text text,
  status text not null default 'in_progress' check (status in ('in_progress','completed','aborted')),
  created_by text not null,
  created_at timestamptz not null default now()
);

create table public.step (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.pipeline_run(id),
  agent_name text not null,
  stage smallint not null check (stage between 1 and 5),
  depends_on_step_ids uuid[] not null default '{}',
  status text not null default 'queued' check (status in
    ('queued','awaiting_launch','running','awaiting_review','accepted','rejected')),
  human_readable_summary text,
  structured_output_refs jsonb not null default '[]',
  launched_by text,
  launched_at timestamptz,
  resolved_by text,
  resolved_at timestamptz,
  pm_note text
);
create index step_run_idx on public.step(run_id);

alter table public.finding add constraint finding_step_fk foreign key (step_id) references public.step(id);

-- ---------- Cluster -> Requirement -> Score ----------
create table public.cluster (
  id uuid primary key default gen_random_uuid(),
  label text not null,
  ontology_domain_id uuid references public.ontology(id),
  step_id uuid references public.step(id),
  created_at timestamptz not null default now()
);
create table public.cluster_finding (
  cluster_id uuid not null references public.cluster(id) on delete cascade,
  finding_id uuid not null references public.finding(id),
  primary key (cluster_id, finding_id)
);

create table public.requirement (
  id uuid primary key default gen_random_uuid(),
  code text unique,                    -- human id, e.g. R-2031
  title text not null,
  description text not null,
  ontology_domain_id uuid references public.ontology(id),
  markets text[] not null default '{}',
  vehicle_line text not null,
  metric text,
  acceptance_criteria text,
  evidence_level text check (evidence_level in ('Verified','Interpreted','Unverified')),
  assumptions text[] not null default '{}',
  uncertainties text[] not null default '{}',
  status text not null default 'draft' check (status in
    ('draft','pm_review','tracked','rejected','challenged','superseded','proposed')),
  origin text not null check (origin in ('scheduled_pipeline','pm_query')),
  created_by_run_id uuid references public.pipeline_run(id),
  step_id uuid references public.step(id),
  created_at timestamptz not null default now()
);
create table public.requirement_finding (
  requirement_id uuid not null references public.requirement(id) on delete cascade,
  finding_id uuid not null references public.finding(id),
  primary key (requirement_id, finding_id)
);
create table public.requirement_cluster (
  requirement_id uuid not null references public.requirement(id) on delete cascade,
  cluster_id uuid not null references public.cluster(id),
  primary key (requirement_id, cluster_id)
);

create table public.score (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirement(id),
  customer_relevance numeric not null,
  business_signal numeric not null,
  strategic_fit numeric not null,
  effort_proxy numeric not null,
  confidence numeric not null,
  composite numeric not null,
  weight_vector_version text not null,
  rationale text,
  computed_by text not null,
  step_id uuid references public.step(id),
  computed_at timestamptz not null default now()
);
create index score_requirement_idx on public.score(requirement_id, computed_at desc);

-- ---------- Audit trail (append-only) ----------
create table public.audit_event (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  actor text not null,
  action text not null,
  before jsonb,
  after jsonb,
  rationale text,
  timestamp timestamptz not null default now()
);
create index audit_event_entity_idx on public.audit_event(entity_type, entity_id);

create function public.audit_event_block_mutation() returns trigger
language plpgsql set search_path = '' as $$
begin
  raise exception 'audit_event is append-only';
end $$;
create trigger audit_event_no_update_delete
  before update or delete on public.audit_event
  for each row execute function public.audit_event_block_mutation();
create trigger audit_event_no_truncate
  before truncate on public.audit_event
  for each statement execute function public.audit_event_block_mutation();

-- ---------- Git -> Supabase docs mirror (see CLAUDE.md) ----------
create table public.design_decisions (
  id text primary key,                 -- e.g. 0001
  title text not null,
  status text,
  body text not null,
  source_path text not null,
  commit_sha text,
  updated_at timestamptz not null default now()
);
create table public.architecture_docs (
  path text primary key,
  title text not null,
  status text,
  body text not null,
  commit_sha text,
  updated_at timestamptz not null default now()
);

-- ---------- RLS: on everywhere; backend uses the service role / direct connection ----------
alter table public.ontology enable row level security;
alter table public.source enable row level security;
alter table public.finding enable row level security;
alter table public.chunk enable row level security;
alter table public.option enable row level security;
alter table public.pipeline_run enable row level security;
alter table public.step enable row level security;
alter table public.cluster enable row level security;
alter table public.cluster_finding enable row level security;
alter table public.requirement enable row level security;
alter table public.requirement_finding enable row level security;
alter table public.requirement_cluster enable row level security;
alter table public.score enable row level security;
alter table public.audit_event enable row level security;
alter table public.design_decisions enable row level security;
alter table public.architecture_docs enable row level security;
