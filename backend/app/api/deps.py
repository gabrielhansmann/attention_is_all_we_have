"""Request-scoped dependencies: a database connection, the orchestrator, and what a background run needs."""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import Annotated

import psycopg
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from psycopg.rows import dict_row

from app.auth import service as auth_service
from app.config import get_settings
from app.orchestration import loop
from app.orchestration.agents import RUNNERS, AgentRunner
from app.orchestration.orchestrator import LLMOrchestrator, Orchestrator, RuleOrchestrator


def get_conn() -> Iterator[psycopg.Connection]:
    """One connection per request. Endpoints that write call conn.commit() themselves, so a response is
    only sent after the data is saved; anything not committed is rolled back when the request ends."""
    settings = get_settings()
    if not settings.db_url:
        raise HTTPException(status_code=503, detail="database not configured")
    try:
        conn = psycopg.connect(settings.db_url, row_factory=dict_row, connect_timeout=10)
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="database unavailable")
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def get_orchestrator() -> Orchestrator:
    """ORCHESTRATOR=llm (default) uses the OpenAI orchestrator; ORCHESTRATOR=rules uses the keyword orchestrator for
    local work without a key. There is no automatic fallback: a missing key is an error the PM can see."""
    if os.environ.get("ORCHESTRATOR", "llm").lower() == "rules":
        return RuleOrchestrator()
    return LLMOrchestrator()


@contextmanager
def _connect() -> Iterator[psycopg.Connection]:
    conn = psycopg.connect(get_settings().db_url, row_factory=dict_row, connect_timeout=10)
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def get_connect() -> Callable[[], AbstractContextManager[psycopg.Connection]]:
    """A connection factory for work that outlives the request: an agent runs after the response is sent,
    when the request's own connection is already closed."""
    return _connect


def get_checkpointer() -> loop.CheckpointerFactory:
    """Where a run's graph state is checkpointed (Postgres). Tests replace it with an in-memory saver."""
    return loop.postgres_checkpointer


def get_runners() -> dict[str, AgentRunner]:
    """The callable behind each catalog agent. Tests replace it with fakes."""
    return RUNNERS


_bearer = HTTPBearer(auto_error=False)
_UNAUTHENTICATED = dict(status_code=401, detail="not authenticated", headers={"WWW-Authenticate": "Bearer"})


def bearer_token(creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)]) -> str:
    """The token from the Authorization header, or 401. Runs before any database access, so a request without a
    token never opens a connection."""
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(**_UNAUTHENTICATED)
    return creds.credentials


def current_user(token: Annotated[str, Depends(bearer_token)],
                 conn: Annotated[psycopg.Connection, Depends(get_conn)]) -> dict:
    """The signed-in user, or 401. Every protected router depends on this. The reason a token is refused
    (unknown, expired, revoked, deactivated user) is never revealed. The token parameter comes first on purpose:
    FastAPI resolves dependencies in order, so a missing token fails before the connection is opened."""
    try:
        user = auth_service.user_for_token(conn, token)
        conn.commit()          # persists the throttled last_used_at refresh
    except psycopg.Error:
        raise HTTPException(status_code=503, detail="database unavailable")
    if user is None:
        raise HTTPException(**_UNAUTHENTICATED)
    return user


User = Annotated[dict, Depends(current_user)]
