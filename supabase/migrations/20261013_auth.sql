-- Authentication: backend-owned users and server-side sessions.
-- Passwords are stored only as scrypt hashes. A session token is random and only its SHA-256 is stored,
-- so a database leak does not yield usable tokens. Users are created by an admin script, never over HTTP.

create table public.app_user (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  display_name text not null,
  password_hash text not null,
  role text not null default 'pm' check (role in ('pm','admin')),
  active boolean not null default true,
  failed_attempts integer not null default 0,
  locked_until timestamptz,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  check (email = lower(email) and position('@' in email) > 1)
);
create unique index app_user_email_key on public.app_user(email);

create table public.auth_session (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.app_user(id) on delete cascade,
  token_hash text not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  last_used_at timestamptz not null default now(),
  revoked_at timestamptz
);
create unique index auth_session_token_key on public.auth_session(token_hash);
create index auth_session_user_idx on public.auth_session(user_id);

alter table public.app_user enable row level security;
alter table public.auth_session enable row level security;
