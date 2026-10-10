-- Messages written in one transaction share the same created_at (now() is frozen per transaction), so
-- created_at cannot order a thread: a request, its plan and a note would come back in random order.
-- A sequence number gives the thread a stable order.
alter table public.message add column seq bigint generated always as identity;
drop index public.message_thread_idx;
create index message_thread_idx on public.message(conversation_id, seq);
