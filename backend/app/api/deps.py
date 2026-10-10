"""Request-scoped dependencies: a database connection, the planner, and what a background step run needs."""
from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.config import get_settings
from app.orchestration.agents import RUNNERS, AgentRunner
from app.orchestration.planner import LLMPlanner, Planner, RulePlanner


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


def get_planner() -> Planner:
    """PLANNER=llm (default) uses the OpenAI planner; PLANNER=rules uses the keyword planner for local work
    without a key. There is no automatic fallback: a missing key is an error the PM can see."""
    if os.environ.get("PLANNER", "llm").lower() == "rules":
        return RulePlanner()
    return LLMPlanner()


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


def get_runners() -> dict[str, AgentRunner]:
    """The callable behind each catalog agent. Tests replace it with fakes."""
    return RUNNERS
