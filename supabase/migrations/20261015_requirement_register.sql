-- Requirement register: the requirements a research run produced, with the PM's decision on each (decision 0022).
-- A snapshot of the accepted Requirements Drafting and Prioritization output is copied here when a run completes,
-- so the PM can review, approve, reject and track requirements without the findings having to be stored first.
-- The cited evidence stays in `payload` (every statement keeps its citations); decisions are audit events.

create sequence public.requirement_register_code_seq;

create table public.requirement_register (
  id uuid primary key,                       -- the drafted requirement's id (stable per cluster)
  code text not null unique default 'R-' || lpad(nextval('public.requirement_register_code_seq')::text, 4, '0'),
  run_id uuid references public.pipeline_run(id),
  conversation_id uuid references public.conversation(id),
  vehicle_line text not null,
  market text not null,
  title text not null,
  status text not null default 'draft' check (status in
    ('draft','pm_review','tracked','rejected','challenged','superseded')),
  payload jsonb not null,                    -- the drafted requirement with its metric, criteria and citations
  score jsonb,                               -- the proposed score and its breakdown, when the run prioritized
  decided_by text,
  decided_at timestamptz,
  decision_note text,
  tracked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index requirement_register_status_idx on public.requirement_register(status, updated_at desc);
create index requirement_register_run_idx on public.requirement_register(run_id);

alter table public.requirement_register enable row level security;
