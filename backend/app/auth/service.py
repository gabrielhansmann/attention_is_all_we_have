"""Users and sessions. Functions take an open psycopg connection (dict rows) and do NOT commit.

Session tokens are random and shown once; only their SHA-256 is stored. Repeated wrong passwords lock the
account for a while. Every failure to log in looks the same from outside.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from .passwords import burn_time, check_policy, hash_password, verify_password

MAX_FAILED = 5
LOCK_MINUTES = 15
TOUCH_EVERY = timedelta(minutes=1)     # how often last_used_at is refreshed


class InvalidCredentials(Exception):
    pass


class AccountLocked(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__("account locked")
        self.retry_after_seconds = retry_after_seconds


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row: dict) -> dict:
    return {k: row[k] for k in ("id", "email", "display_name", "role")}


# ---------------------------------------------------------------- users (admin script only)

def create_user(conn, email: str, display_name: str, password: str, role: str = "pm") -> dict:
    email = normalize_email(email)
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise ValueError("that does not look like an email address")
    if not display_name.strip():
        raise ValueError("a display name is required")
    if role not in ("pm", "admin"):
        raise ValueError("role must be pm or admin")
    check_policy(password)
    if conn.execute("select 1 from public.app_user where email = %s", (email,)).fetchone():
        raise ValueError("a user with that email already exists")
    return conn.execute(
        "insert into public.app_user (email, display_name, password_hash, role) values (%s,%s,%s,%s) returning *",
        (email, display_name.strip(), hash_password(password), role)).fetchone()


def set_password(conn, email: str, password: str) -> None:
    """New password; every existing session of that user is revoked."""
    check_policy(password)
    row = conn.execute(
        "update public.app_user set password_hash = %s, failed_attempts = 0, locked_until = null "
        "where email = %s returning id", (hash_password(password), normalize_email(email))).fetchone()
    if not row:
        raise ValueError("no such user")
    conn.execute("update public.auth_session set revoked_at = now() where user_id = %s and revoked_at is null",
                 (row["id"],))


def set_active(conn, email: str, active: bool) -> None:
    row = conn.execute("update public.app_user set active = %s where email = %s returning id",
                       (active, normalize_email(email))).fetchone()
    if not row:
        raise ValueError("no such user")
    if not active:
        conn.execute("update public.auth_session set revoked_at = now() where user_id = %s and revoked_at is null",
                     (row["id"],))


def list_users(conn) -> list[dict]:
    return conn.execute("select email, display_name, role, active, last_login_at, locked_until "
                        "from public.app_user order by email").fetchall()


# ---------------------------------------------------------------- login and sessions

def authenticate(conn, email: str, password: str) -> dict:
    """The user row on success. Raises InvalidCredentials (wrong password, unknown or inactive account, all
    indistinguishable) or AccountLocked. The caller must commit before turning the exception into a response,
    because the failed-attempt counter has to persist."""
    # Serialize attempts for one account: concurrent wrong passwords must not overwrite each other's counter.
    user = conn.execute("select * from public.app_user where email = %s for update", (normalize_email(email),)).fetchone()
    if user is None:
        burn_time()
        raise InvalidCredentials()
    now = datetime.now(timezone.utc)
    if user["locked_until"] and user["locked_until"] > now:
        raise AccountLocked(int((user["locked_until"] - now).total_seconds()) + 1)
    if not verify_password(password, user["password_hash"]) or not user["active"]:
        failed = user["failed_attempts"] + 1
        if failed >= MAX_FAILED:
            conn.execute("update public.app_user set failed_attempts = 0, locked_until = %s where id = %s",
                         (now + timedelta(minutes=LOCK_MINUTES), user["id"]))
        else:
            conn.execute("update public.app_user set failed_attempts = %s where id = %s", (failed, user["id"]))
        raise InvalidCredentials()
    conn.execute("update public.app_user set failed_attempts = 0, locked_until = null, last_login_at = now() "
                 "where id = %s", (user["id"],))
    return user


def create_session(conn, user_id, hours: int) -> tuple[str, datetime]:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=hours)
    conn.execute("insert into public.auth_session (user_id, token_hash, expires_at) values (%s,%s,%s)",
                 (user_id, _token_hash(token), expires))
    return token, expires


def user_for_token(conn, token: str) -> dict | None:
    """The active user behind a valid, unexpired, unrevoked session; None otherwise. Refreshes last_used_at at
    most once a minute (the caller commits)."""
    row = conn.execute(
        "select s.id as session_id, s.last_used_at, u.* from public.auth_session s "
        "join public.app_user u on u.id = s.user_id "
        "where s.token_hash = %s and s.revoked_at is null and s.expires_at > now() and u.active",
        (_token_hash(token),)).fetchone()
    if row is None:
        return None
    if datetime.now(timezone.utc) - row["last_used_at"] > TOUCH_EVERY:
        conn.execute("update public.auth_session set last_used_at = now() where id = %s", (row["session_id"],))
    return row


def revoke_token(conn, token: str) -> None:
    conn.execute("update public.auth_session set revoked_at = now() where token_hash = %s and revoked_at is null",
                 (_token_hash(token),))
