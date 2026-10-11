"""A failed database test must not expose the connection exception or its local parameters."""
import psycopg
import pytest


def test_database_fixture_failure_does_not_chain_connection_details(monkeypatch):
    import conftest
    monkeypatch.setattr(conftest,'HAS_DB',True)
    def fail(*args,**kwargs):
        raise psycopg.OperationalError('synthetic-sensitive-connection-detail')
    monkeypatch.setattr(psycopg,'connect',fail)
    with pytest.raises(pytest.fail.Exception) as caught:
        next(conftest.db.__wrapped__())
    assert caught.value.__context__ is None
    assert 'synthetic-sensitive-connection-detail' not in str(caught.value)
