"""Adding a website: which addresses are fetched, what text is kept, the endpoints, and a real load rolled back."""
import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import library as library_api
from app.api.deps import get_ingest_conn
from app.ingest import load_web, upload
from app.main import app

client = TestClient(app)

PAGE = """<html><head><title>Test Drive: The New Sedan</title><style>p { color: red }</style></head><body>
<nav><a href="/">Home</a> <a href="/news">News</a></nav>
<h1>Test Drive</h1>
<p>The cabin is quiet at motorway speed and the seats stay comfortable over a long day of driving.</p>
<script>track("pageview")</script>
<h2>Infotainment</h2>
<p>The voice assistant often misunderstands navigation requests, which owners describe as distracting.</p>
<p>Wireless phone mirroring connects quickly &amp; stays stable.</p>
<footer>Copyright, imprint, cookie settings and a long list of links nobody should cite.</footer>
</body></html>"""


class FakeEmbeddings:
    def create(self, model, input):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1536) for _ in input])


FAKE_OPENAI = SimpleNamespace(embeddings=FakeEmbeddings())


class NoQueries:
    def execute(self, *a, **k):
        pytest.fail("a refused address must not reach the database")


# ---------------------------------------------------------------- address and text

@pytest.mark.parametrize("url", ["ftp://example.com/a", "file:///etc/passwd", "example.com/page", "https://", "",
                                 "https://user:pw@example.com/"])
def test_only_plain_http_addresses_are_accepted(url):
    with pytest.raises(upload.UploadError):
        load_web.ingest_website(NoQueries(), url)


def test_the_stored_address_has_no_fragment_and_a_lower_case_host():
    assert load_web.normalize_url(" HTTPS://Example.COM/Path?q=1#top ") == "https://example.com/Path?q=1"
    assert load_web.normalize_url("http://example.com") == "http://example.com/"


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"])
def test_addresses_inside_the_network_are_never_fetched(address, monkeypatch):
    monkeypatch.setattr(load_web.socket, "getaddrinfo", lambda *a, **k: [(None, None, None, "", (address, 0))])
    monkeypatch.setattr(load_web.urllib.request, "build_opener",
                        lambda *a: SimpleNamespace(open=lambda *a, **k: pytest.fail("must not connect")))
    with pytest.raises(upload.UploadError, match="public internet"):
        load_web.fetch_page("https://intranet.example/")


def test_a_redirect_to_an_inside_address_is_refused(monkeypatch):
    import urllib.error
    from email.message import Message

    monkeypatch.setattr(load_web.socket, "getaddrinfo", lambda host, *a, **k: [
        (None, None, None, "", ("10.0.0.5" if host == "inside.example" else "93.184.216.34", 0))])
    headers = Message()
    headers["Location"] = "http://inside.example/admin"

    def open_(req, timeout):
        assert "inside.example" not in req.full_url, "must not connect to the redirect target"
        raise urllib.error.HTTPError(req.full_url, 302, "Found", headers, None)
    monkeypatch.setattr(load_web.urllib.request, "build_opener", lambda *a: SimpleNamespace(open=open_))
    with pytest.raises(upload.UploadError, match="public internet"):
        load_web.fetch_page("https://outside.example/")


def test_text_is_kept_under_its_heading_without_scripts_navigation_or_footer():
    title, blocks = load_web.extract("text/html", PAGE)
    chunks = load_web.passages(title, blocks)
    assert title == "Test Drive: The New Sedan"
    assert [(c.page, c.heading) for c in chunks] == [(1, "Test Drive"), (2, "Infotainment")]
    assert "quiet at motorway speed" in chunks[0].text
    assert chunks[1].text.endswith("connects quickly & stays stable.")
    text = " ".join(c.text for c in chunks)
    assert all(word not in text for word in ("pageview", "cookie", "Home", "color: red"))
    assert chunks[1].embed_input.startswith("Test Drive: The New Sedan — Infotainment\n")


def test_a_long_block_is_cut_into_passages_at_sentence_ends():
    long = " ".join(f"Sentence number {i} says something about the car." for i in range(120))
    chunks = load_web.passages("T", [(None, long)])
    assert len(chunks) > 2 and all(len(c.text) <= load_web.MAX_CHARS for c in chunks)
    assert all(c.text.endswith(".") for c in chunks) and [c.page for c in chunks] == list(range(1, len(chunks) + 1))


# ---------------------------------------------------------------- endpoints, no database

@pytest.fixture
def no_conn():
    app.dependency_overrides[get_ingest_conn] = lambda: None
    yield
    app.dependency_overrides.pop(get_ingest_conn, None)


def test_the_endpoint_hands_the_address_to_the_loader(no_conn, monkeypatch):
    seen = {}

    def fake(conn, url, **kwargs):
        seen.update(url=url, **kwargs)
        return {"file": url, "kind": "web", "replaced": False, "notes": [],
                "counts": {"feedback": 0, "pdf_chunks": 4, "options": 0, "study_cells": 0, "sales_rows": 0}}
    monkeypatch.setattr(library_api.load_web, "ingest_website", fake)
    r = client.post("/api/sources/web", json={"url": "https://example.com/a", "line": "G60", "trust_tier": "trade_press"})
    assert r.status_code == 201 and r.json()["kind"] == "web" and r.json()["counts"]["pdf_chunks"] == 4
    assert seen == {"url": "https://example.com/a", "line": "G60", "market": None, "trust_tier": "trade_press", "replace": False}
    assert client.post("/api/sources/web", json={"url": "https://example.com/a", "trust_tier": "mine"}).status_code == 422


def test_refusals_keep_their_status_and_outages_hide_details(no_conn, monkeypatch):
    def refuse(*a, **k):
        raise upload.AlreadyLoaded("This page is already stored.")
    monkeypatch.setattr(library_api.load_web, "ingest_website", refuse)
    r = client.post("/api/sources/web", json={"url": "https://example.com/a"})
    assert r.status_code == 409 and r.json()["detail"] == "This page is already stored."

    def boom(*a, **k):
        raise RuntimeError("password=secret host=db.example")
    monkeypatch.setattr(library_api.load_web, "ingest_website", boom)
    monkeypatch.setattr(library_api.load_web, "remove_website", boom)
    monkeypatch.setattr(library_api.library, "source_graph", boom)
    monkeypatch.setattr(library_api.library, "web_research", boom)
    for r in (client.post("/api/sources/web", json={"url": "https://example.com/a"}),
              client.delete("/api/sources/00000000-0000-0000-0000-000000000000"),
              client.get("/api/sources/graph"), client.get("/api/sources/web-research")):
        assert r.status_code == 503 and "secret" not in r.text


# ---------------------------------------------------------------- real load, rolled back

@pytest.fixture
def conn():
    """Plain rows as the loaders expect. Nothing is committed: their transaction blocks become savepoints."""
    if not os.environ.get("SUPABASE_DB_URL"):
        pytest.skip("SUPABASE_DB_URL not set")
    import psycopg
    c = psycopg.connect(os.environ["SUPABASE_DB_URL"], connect_timeout=10)
    try:
        yield c
    finally:
        c.rollback()
        c.close()


URL = "https://web-source-test.example/review"


def test_a_page_is_stored_as_cited_passages_replaced_and_removed(conn):
    fetch = lambda url: ("text/html", PAGE)
    out = load_web.ingest_website(conn, URL + "#comments", line="G60", market="EU", client=FAKE_OPENAI, fetch=fetch)
    assert out == {"file": URL, "kind": "web", "replaced": False, "notes": [],
                   "counts": {"feedback": 0, "pdf_chunks": 2, "options": 0, "study_cells": 0, "sales_rows": 0}}
    sid, type_, line, market, tier, title = conn.execute(
        "select id, type, vehicle_line, market, trust_tier, title from public.source where uri = %s", (URL,)).fetchone()
    assert (type_, line, market, tier, title) == ("web", "G60", "EU", "forum_social", "Test Drive: The New Sedan")
    rows = conn.execute("select page, locator, heading, embedding is not null from public.chunk "
                        "where source_id = %s order by page", (sid,)).fetchall()
    assert rows == [(1, "passage 1", "Test Drive", True), (2, "passage 2", "Infotainment", True)]
    # Evidence search and the agents read chunks through this view, so a web passage must be citable there.
    assert conn.execute("select kind, file, locator, vehicle_line from public.evidence_item where file = %s "
                        "order by locator", (URL,)).fetchall() == [("pdf_text", URL, "page 1", "G60"), ("pdf_text", URL, "page 2", "G60")]

    with pytest.raises(upload.AlreadyLoaded):
        load_web.ingest_website(conn, URL, client=FAKE_OPENAI, fetch=fetch)
    again = load_web.ingest_website(conn, URL, trust_tier="trade_press", replace=True, client=FAKE_OPENAI,
                                    fetch=lambda url: ("text/plain", "One paragraph of plain text that is long enough to keep."))
    assert again["replaced"] is True and again["counts"]["pdf_chunks"] == 1
    assert conn.execute("select trust_tier, vehicle_line from public.source where id = %s", (sid,)).fetchone() == ("trade_press", None)

    load_web.remove_website(conn, str(sid))
    assert conn.execute("select count(*) from public.source where uri = %s", (URL,)).fetchone()[0] == 0


def test_nothing_is_stored_for_an_empty_page_an_unknown_scope_or_a_file(conn):
    with pytest.raises(upload.UploadError, match="No readable text"):
        load_web.ingest_website(conn, URL, client=FAKE_OPENAI, fetch=lambda url: ("text/html", "<html><body><script>app()</script></body></html>"))
    with pytest.raises(upload.UploadError, match="Unknown vehicle line"):
        load_web.ingest_website(conn, URL, line="E39", client=FAKE_OPENAI, fetch=lambda url: pytest.fail("must not fetch"))
    assert conn.execute("select count(*) from public.source where uri = %s", (URL,)).fetchone()[0] == 0
    file_id = conn.execute("select id from public.source where type <> 'web' limit 1").fetchone()[0]
    with pytest.raises(LookupError):
        load_web.remove_website(conn, str(file_id))        # files are never removed through this route


def test_the_graph_links_each_source_to_what_it_covers_and_web_research_reads_step_outputs(db):
    links = client.get("/api/sources/graph").json()["links"]
    by_file = {s["id"]: s["file"] for s in client.get("/api/sources").json()}
    g60 = [l for l in links if by_file[l["source_id"]] == "G60_feedback_hackathon.xlsx"]
    assert sum(l["rows"] for l in g60) == 5005 and {l["line"] for l in g60} == {"G60"}
    assert {l["market"] for l in g60} >= {"US", "EU"}
    catalog = [l for l in links if by_file[l["source_id"]] == "G60_OptionList.PDF"]
    assert len(catalog) == 1 and catalog[0]["line"] == "G60" and catalog[0]["market"] is None and catalog[0]["rows"] > 62

    sites = client.get("/api/sources/web-research")
    assert sites.status_code == 200
    assert all(s["url"].startswith("http") and s["domain"] and s["agent"] in ("Market & Trend Agent", "Competitor Agent")
               for s in sites.json())
    assert len({s["url"] for s in sites.json()}) == len(sites.json())
