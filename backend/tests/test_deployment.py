"""Frontend delivery must preserve API authentication and HTTP errors."""
from fastapi.testclient import TestClient

from app.deploy.vercel import create_deployment_app


def test_deployment_serves_frontend_without_bypassing_api_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    (tmp_path / "index.html").write_text('<html><div id="root">Frontend</div></html>')
    (tmp_path / "bundle.js").write_text('console.log("frontend")')
    client = TestClient(create_deployment_app(tmp_path))
    assert client.get("/", headers={"Accept": "text/html"}).status_code == 200
    assert client.get("/bundle.js").headers['content-type'].startswith('text/javascript')
    # A browser navigation header must not turn the API's sign-in gate into an HTML 200.
    assert client.get("/api/models", headers={"Accept": "text/html"}).status_code == 401


def test_frontend_keeps_missing_files_and_disabled_docs_visible(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    (tmp_path / "index.html").write_text('<html><div id="root">Frontend</div></html>')
    client = TestClient(create_deployment_app(tmp_path))
    assert client.get("/missing.js", headers={"Accept": "text/html"}).status_code == 404
    assert client.get("/docs", headers={"Accept": "application/json"}).status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cdn_only_frontend_does_not_break_backend_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client = TestClient(create_deployment_app(tmp_path / "cdn-only"))
    for path in ("/", "/missing.js", "/docs", "/openapi.json", "/api/unknown"):
        assert client.get(path, headers={"Accept": "text/html"}).status_code == 404
    assert client.get("/api/models", headers={"Accept": "text/html"}).status_code == 401
