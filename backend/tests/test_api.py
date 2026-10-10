"""API tests run without a database or OpenAI key: the knowledge tools are replaced with fakes."""
import pytest
from fastapi.testclient import TestClient

from app.api import evidence, health
from app.knowledge.tools import Citation, Hit
from app.main import app

client = TestClient(app)


def fake_hit(kind="feedback"):
    return Hit(Citation(kind, "11111111-1111-1111-1111-111111111111", "G60_feedback_hackathon.xlsx",
                        "sheet Feedback_Explorer, row 4642 (G60-3695)", "They barely cool anything"),
               "They barely cool anything", {"vehicle_line": "G60", "similarity": 0.71}, 0.03)


def test_health_reports_degraded_without_services(monkeypatch):
    monkeypatch.setattr(health, "check_db", lambda: "not_configured")
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db"] == "not_configured"
    assert body["status"] == "degraded"
    assert "postgres" not in r.text.lower() and "password" not in r.text.lower()


def test_search_returns_hits_with_citations(monkeypatch):
    seen = {}

    def fake(q, **kw):
        seen.update(q=q, **kw)
        return [fake_hit()]

    monkeypatch.setattr(evidence.tools, "search_feedback", fake)
    r = client.get("/api/evidence/search", params={"q": "seat ventilation", "line": "G60", "polarity": "negative"})
    assert r.status_code == 200
    hit = r.json()["hits"][0]
    assert hit["citation"]["file"] == "G60_feedback_hackathon.xlsx"
    assert hit["citation"]["locator"].startswith("sheet Feedback_Explorer, row 4642")
    assert hit["citation"]["quote"]
    assert seen["line"] == "G60" and seen["polarity"] == "negative" and seen["k"] == 10


def test_docs_source_uses_docs_search(monkeypatch):
    monkeypatch.setattr(evidence.tools, "search_docs", lambda q, **kw: [fake_hit("pdf_text")])
    r = client.get("/api/evidence/search", params={"q": "Felgen", "source": "docs"})
    assert r.json()["source"] == "docs" and r.json()["hits"][0]["citation"]["kind"] == "pdf_text"


@pytest.mark.parametrize("params", [
    {"q": "x"},                                      # too short
    {"q": "   "},                                    # whitespace must not reach embeddings
    {"q": " x "},                                    # length is checked after trimming
    {"q": "seats", "line": "X99"},                   # unknown line
    {"q": "seats", "market": "MARS"},                # unknown market
    {"q": "seats", "k": 500},                        # too many
    {"q": "seats", "source": "tables"},              # unknown source
])
def test_bad_parameters_are_rejected_before_any_lookup(params, monkeypatch):
    monkeypatch.setattr(evidence.tools, "search_feedback", lambda *a, **k: pytest.fail("must not be called"))
    assert client.get("/api/evidence/search", params=params).status_code == 422


def test_unknown_domain_is_a_422(monkeypatch):
    def boom(*a, **k):
        raise ValueError("unknown domain: nope")
    monkeypatch.setattr(evidence.tools, "search_feedback", boom)
    r = client.get("/api/evidence/search", params={"q": "seats", "domain": "nope"})
    assert r.status_code == 422 and "unknown domain" in r.json()["detail"]


def test_store_outage_is_a_503_without_details(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("password=secret host=db.example")
    monkeypatch.setattr(evidence.tools, "search_feedback", boom)
    r = client.get("/api/evidence/search", params={"q": "seats"})
    assert r.status_code == 503
    assert "secret" not in r.text and "db.example" not in r.text


def test_stats_sums_the_total(monkeypatch):
    monkeypatch.setattr(evidence.tools, "feedback_stats",
                        lambda group_by, **kw: [{"key": "US", "n": 1594}, {"key": "EU", "n": 72}])
    body = client.get("/api/evidence/stats", params={"group_by": "market_code", "line": "G60"}).json()
    assert body["total"] == 1666 and body["rows"][0] == {"key": "US", "n": 1594}


def test_cite_unknown_row_is_404_and_bad_id_is_422(monkeypatch):
    def missing(kind, id):
        raise LookupError("nope")
    monkeypatch.setattr(evidence.tools, "cite", missing)
    assert client.get("/api/evidence/feedback/00000000-0000-0000-0000-000000000000").status_code == 404
    assert client.get("/api/evidence/feedback/not-a-uuid").status_code == 422
    assert client.get("/api/evidence/spreadsheet/00000000-0000-0000-0000-000000000000").status_code == 422
