-- Chat entry point and orchestrator-planned steps (decision 0005, docs/architecture/02 and 04).
-- step and pipeline_run were empty when this was applied, so the state change needs no data migration.

-- ---------- conversation + message ----------
create table public.conversation (
  id uuid primary key default gen_random_uuid(),
  title text not null,
  created_by text not null default 'pm',
  vehicle_line text,                      -- scope read from the PM's message, or null until known
  market_code text,
  status text not null default 'active' check (status in ('active','archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index conversation_recent_idx on public.conversation(status, updated_at desc);

create table public.message (
  id uuid primary key default gen_random_uuid(),
  conversation_id uuid not null references public.conversation(id) on delete cascade,
  role text not null check (role in ('pm','orchestrator','agent','system')),
  kind text not null check (kind in
    ('request','plan','plan_change','step_card','pushback','final_result','system_note')),
  run_id uuid references public.pipeline_run(id),
  step_id uuid references public.step(id),
  content text not null,                  -- human-readable text shown in the thread
  payload jsonb not null default '{}'::jsonb,   -- structured data for the card (plan items, citations, summary parts)
  created_at timestamptz not null default now(),
  -- a step card and a pushback always belong to a step
  check (kind not in ('step_card','pushback') or step_id is not null)
);
create index message_thread_idx on public.message(conversation_id, created_at);
create index message_run_idx on public.message(run_id);
create index message_step_idx on public.message(step_id);

-- a new message moves the conversation to the top of the list
create function public.touch_conversation() returns trigger
language plpgsql set search_path = '' as $$
begin
  update public.conversation set updated_at = now() where id = new.conversation_id;
  return new;
end $$;
create trigger message_touch_conversation
  after insert on public.message for each row execute function public.touch_conversation();

-- ---------- pipeline_run belongs to a conversation ----------
alter table public.pipeline_run add column conversation_id uuid references public.conversation(id);
create index pipeline_run_conversation_idx on public.pipeline_run(conversation_id);

-- ---------- step: new states, plan fields, one active step per run ----------
alter table public.step drop constraint step_status_check;
alter table public.step alter column status set default 'planned';
alter table public.step add constraint step_status_check
  check (status in ('planned','running','awaiting_review','accepted','rejected'));
alter table public.step
  add column position integer not null,                 -- order in the plan, starting at 1
  add column plan_reason text,                          -- why the orchestrator included this agent
  add column planned_by text not null default 'orchestrator' check (planned_by in ('orchestrator','pm')),
  add column attempt integer not null default 1;        -- incremented by every Retry
create unique index step_run_position_key on public.step(run_id, position);
-- agents run strictly one at a time: nothing may start while another step is running or in review
create unique index step_one_active_per_run on public.step(run_id)
  where status in ('running','awaiting_review');

alter table public.conversation enable row level security;
alter table public.message enable row level security;
