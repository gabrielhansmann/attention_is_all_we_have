-- LangGraph checkpoint tables (decision 0019). The orchestration loop runs as a LangGraph graph with
-- thread_id = pipeline_run.id; these tables hold its control-flow state so a run can resume after a restart.
-- This is the schema of langgraph-checkpoint-postgres (its MIGRATIONS 0-9) written out here, so the app never runs
-- DDL by itself: it does not call PostgresSaver.setup(). The pipeline_run, step and message tables stay the record
-- of what happened; nothing the UI shows is read from these tables.
-- Dropping them loses only the ability to resume runs that are in progress.

create table if not exists public.checkpoint_migrations (v integer primary key);

create table if not exists public.checkpoints (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb not null,
  metadata jsonb not null default '{}',
  primary key (thread_id, checkpoint_ns, checkpoint_id)
);

create table if not exists public.checkpoint_blobs (
  thread_id text not null,
  checkpoint_ns text not null default '',
  channel text not null,
  version text not null,
  type text not null,
  blob bytea,
  primary key (thread_id, checkpoint_ns, channel, version)
);

create table if not exists public.checkpoint_writes (
  thread_id text not null,
  checkpoint_ns text not null default '',
  checkpoint_id text not null,
  task_id text not null,
  idx integer not null,
  channel text not null,
  type text,
  blob bytea not null,
  task_path text not null default '',
  primary key (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

create index if not exists checkpoints_thread_id_idx on public.checkpoints(thread_id);
create index if not exists checkpoint_blobs_thread_id_idx on public.checkpoint_blobs(thread_id);
create index if not exists checkpoint_writes_thread_id_idx on public.checkpoint_writes(thread_id);

-- the library's own version bookkeeping, so a later setup() call would find nothing to do
insert into public.checkpoint_migrations (v) select generate_series(0, 9) on conflict do nothing;

-- RLS on everywhere, as for every other table; the backend connects directly
alter table public.checkpoint_migrations enable row level security;
alter table public.checkpoints enable row level security;
alter table public.checkpoint_blobs enable row level security;
alter table public.checkpoint_writes enable row level security;
