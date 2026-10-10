# 0016 — Backend-owned users and server-side sessions protect the whole API

> Date: 2026-10-13 · Status: accepted

## Context

The API was open: anyone who could reach it could read the stored BMW evidence, create conversations that cannot be
deleted (the audit log is append-only) and trigger planner calls that cost OpenAI money. The audit trail also needs to
say who acted, and until now every action was recorded as "pm". Options considered: Supabase Auth, our own users, or a
single shared token. The team chose its own users and tokens.

## Decision

1. **Own users, in the database.** `app_user` holds a scrypt password hash (standard library, no extra dependency;
   12 to 256 characters). Users are created only by an administrator with `python -m app.auth.manage`, with the password
   typed at a hidden prompt. There is no sign-up or admin endpoint.
2. **Server-side sessions, not self-contained tokens.** Login returns a random token; only its SHA-256 is stored, so a
   database leak yields no usable tokens. Sessions expire (`AUTH_SESSION_HOURS`, default 12) and can be revoked: logout,
   changing a password and deactivating a user all end the sessions concerned immediately, which a signed token cannot do.
3. **Protected by default.** Every router except health and login sits under one dependency (`current_user`). A test
   walks every route and requires a 401 without a token, so a new endpoint cannot be left open by accident.
4. **A missing token never reaches the database**: the token is read first, and only then is a connection opened.
5. **Uniform failures.** Wrong password, unknown email and inactive account all answer the same 401, and an unknown email
   costs the same time as a real check. A refused token never says why. Five wrong passwords lock the account for 15
   minutes (429 with `Retry-After`).
6. **Identity in the audit trail.** The signed-in email is stored as creator and actor on conversations, runs, plan edits
   and PM messages, and as the actor of every step action (accept, retry, edit, reject, abort) and in `resolved_by` /
   `launched_by` on the step. System events keep the system as actor. Starting a run records no separate audit event yet.
7. **Frontend.** The live views show a sign-in form when the API answers 401. The token lives in `sessionStorage`, is sent
   as a Bearer header and is dropped on any 401. The offline demo needs no sign-in and never calls these endpoints.
8. **Production mode** (`APP_ENV=production`) turns off the interactive API docs and the OpenAPI document.

## Consequences

- Conversations are visible to every signed-in user (a shared team workspace). Per-user privacy is not modelled; roles
  (`pm`, `admin`) exist but only mark who an administrator is. No endpoint checks the role yet.
- The lockout can be used to lock a known account out by guessing wrong passwords for it (a denial of service). It is
  accepted for a small invited team; a per-address limit belongs in front of the API when it is hosted.
- The 429 reply appears only after five failed tries on one email, so it does reveal that this account exists. Wrong
  password, unknown email and inactive account are otherwise identical.
- No password reset by email: an administrator runs `set-password`.
- A token in `sessionStorage` is readable by any script on the page, which is why the app ships no third-party scripts.
  A cookie-based session with CSRF protection is the alternative if that changes.
- Each authenticated request makes one extra database round trip (session lookup). A cache or pool is the fix if it matters.
- Hosting still needs HTTPS (tokens travel in a header), a CORS origin list and secrets in the host's settings.

See [`../architecture/12-repo-structure.md`](../architecture/12-repo-structure.md).
