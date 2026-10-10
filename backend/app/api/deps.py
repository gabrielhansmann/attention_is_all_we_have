"""Request-scoped dependencies: a database connection and the planner."""
from __future__ import annotations

import os
from collections.abc import Iterator

import psycopg
from fastapi import HTTPException
from psycopg.rows import dict_row

from app.config import get_settings
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
