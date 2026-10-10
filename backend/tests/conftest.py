import os
from uuid import UUID

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


TEST_USER = {"id": UUID("00000000-0000-0000-0000-0000000000aa"), "email": "tester@example.com",
             "display_name": "Test User", "role": "pm"}


@pytest.fixture(autouse=True)
def signed_in(request):
    """Most tests are about something other than sign-in, so the protected routes see a test user. Tests marked
    `real_auth` run the real dependency instead."""
    from app.api.deps import current_user
    from app.main import app

    if request.node.get_closest_marker("real_auth"):
        yield
        return
    app.dependency_overrides[current_user] = lambda: TEST_USER
    yield
    app.dependency_overrides.pop(current_user, None)
