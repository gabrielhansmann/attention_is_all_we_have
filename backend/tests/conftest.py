import os

import pytest

from app.config import load_env

load_env()
HAS_DB = bool(os.environ.get("SUPABASE_DB_URL"))


@pytest.fixture
def db():
    """A real connection to the project database whose work is ALWAYS rolled back, so tests leave no rows.
    The wrapper turns commit/rollback inside the code under test into no-ops; the fixture rolls back at the end."""
    if not HAS_DB:
        pytest.skip("SUPABASE_DB_URL not set")
    import psycopg
    from psycopg.rows import dict_row

    conn = psycopg.connect(os.environ["SUPABASE_DB_URL"], row_factory=dict_row, connect_timeout=10)

    class Wrapped:
        def __getattr__(self, name):
            return getattr(conn, name)

        def commit(self):
            pass

        def rollback(self):
            pass

    try:
        yield Wrapped()
    finally:
        conn.rollback()
        conn.close()
