"""Every route is protected unless it is on the allow-list, and a request without a token never touches the database.
These tests need no database."""
import re

import pytest
from fastapi.testclient import TestClient

from app.api import deps
from app.main import app

pytestmark = pytest.mark.real_auth

PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login")}
SAMPLE = "00000000-0000-0000-0000-000000000001"


def all_routes():
    out = []
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            out.append((method.upper(), path))
    return sorted(out)


@pytest.fixture
def no_db(monkeypatch):
    """Any attempt to open a database connection fails the test."""
    def boom(*a, **k):
        raise AssertionError("an unauthenticated request must not open a database connection")
    monkeypatch.setattr(deps.psycopg, "connect", boom)


def test_the_api_has_routes_to_check():
    assert len(all_routes()) >= 19       # guards against this test passing because the route list came back empty


@pytest.mark.parametrize("method,path", [r for r in all_routes() if r not in PUBLIC])
def test_every_non_public_route_refuses_requests_without_a_token(method, path, no_db):
    url = re.sub(r"\{kind\}", "feedback", path)
    url = re.sub(r"\{[a-z_]+\}", SAMPLE, url)           # every other path parameter is a UUID
    r = TestClient(app).request(method, url, json={} if method in ("POST", "PUT", "PATCH") else None)
    assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a token"
    assert r.headers.get("www-authenticate") == "Bearer"
    assert r.json() == {"detail": "not authenticated"}


@pytest.mark.parametrize("header", ["Bearer", "Basic dXNlcjpwYXNz", "Token abc", "bearer "])
def test_malformed_authorization_headers_are_refused_without_a_database(header, no_db):
    r = TestClient(app).get("/api/agents", headers={"Authorization": header})
    assert r.status_code == 401


def test_health_stays_public(monkeypatch):
    monkeypatch.setattr("app.api.health.check_db", lambda: "ok")
    assert TestClient(app).get("/api/health").status_code == 200


def test_interactive_docs_are_off_in_production(monkeypatch):
    from app.main import create_app
    monkeypatch.setenv("APP_ENV", "production")
    prod = TestClient(create_app())
    assert prod.get("/docs").status_code == 404 and prod.get("/openapi.json").status_code == 404
    monkeypatch.delenv("APP_ENV")
    assert TestClient(create_app()).get("/openapi.json").status_code == 200
