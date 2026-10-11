"""The optional catalog endpoint stays cited, bounded and authenticated by the global guard."""
import pytest
from fastapi.testclient import TestClient

from app.api import market_impact
from app.knowledge.tools import Citation, Hit
from app.main import app

client = TestClient(app)


def test_catalog_reads_optional_options_for_requested_line(monkeypatch):
    seen = {}
    hit = Hit(Citation("option", "option-id", "catalog.pdf", "page 3, SA 453", "Seat ventilation"),
              "Seat ventilation", {"code": "453"}, None)

    def fake(**kwargs):
        seen.update(kwargs)
        return [hit] * 201

    monkeypatch.setattr(market_impact.tools, "get_options", fake)
    response = client.get("/api/market-impact/options?line=G60")
    assert response.status_code == 200
    assert seen == {"line": "G60", "status": "optional", "limit": 201}
    body = response.json()
    assert len(body["options"]) == 200 and body["truncated"] is True
    assert body["options"][0]["citation"]["quote"] == "Seat ventilation"


def test_empty_catalog_is_not_a_forecast(monkeypatch):
    monkeypatch.setattr(market_impact.tools, "get_options", lambda **kwargs: [])
    assert client.get("/api/market-impact/options?line=F70").json() == {
        "line": "F70", "options": [], "truncated": False}


@pytest.mark.parametrize("query", ["", "?line=X99"])
def test_invalid_line_does_not_open_store(query, monkeypatch):
    monkeypatch.setattr(market_impact.tools, "get_options", lambda **kwargs: pytest.fail("must not query"))
    assert client.get(f"/api/market-impact/options{query}").status_code == 422


def test_outage_does_not_expose_connection_details(monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("password=secret host=private")

    monkeypatch.setattr(market_impact.tools, "get_options", fail)
    response = client.get("/api/market-impact/options?line=G60")
    assert response.status_code == 503
    assert "secret" not in response.text and "private" not in response.text


def test_assessment_endpoint_returns_cited_directional_results(monkeypatch):
    seen = {}

    def assess(line, **kwargs):
        seen.update(line=line, **kwargs)
        return {"line": line, "feature": "Seat ventilation", "catalog_citation": None, "basis": "Local feedback signal",
                "query_terms": ["seat ventilation"], "markets": [{"market": "US", "direction": "positive",
                "explanation": "Customer request", "total_feedback": 12, "matched_total": 1,
                "counts": {"positive": 0, "request": 1, "negative": 0}, "reviewed": 1,
                "evidence": [{"citation": {"kind": "feedback", "id": "f1", "file": "feedback.xlsx", "locator": "row 1", "quote": "Want ventilated seats"},
                              "stance": "supports", "reason": "Request"}]}]}

    monkeypatch.setattr(market_impact.market_impact_agent, "assess", assess)
    response = client.post("/api/market-impact/assessment", json={"line": "G60", "feature": " Seat ventilation "})
    assert response.status_code == 200
    assert seen == {"line": "G60", "feature": "Seat ventilation", "option_id": None}
    assert response.json()["markets"][0]["evidence"][0]["citation"]["quote"]


@pytest.mark.parametrize("body", [{"line": "G60"}, {"line": "X99", "feature": "seats"},
    {"line": "G60", "feature": "  "}, {"line": "G60", "option_id": "bad"},
    {"line": "G60", "option_id": "00000000-0000-0000-0000-000000000001", "feature": "seats"}])
def test_bad_assessment_input_does_not_open_store(body, monkeypatch):
    monkeypatch.setattr(market_impact.market_impact_agent, "assess", lambda *args, **kwargs: pytest.fail("must not run"))
    assert client.post("/api/market-impact/assessment", json=body).status_code == 422


def test_assessment_outage_and_missing_option_are_visible_without_secrets(monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError("password=secret host=private")

    monkeypatch.setattr(market_impact.market_impact_agent, "assess", fail)
    response = client.post("/api/market-impact/assessment", json={"line": "G60", "feature": "seats"})
    assert response.status_code == 503 and "secret" not in response.text and "private" not in response.text

    def missing(*args, **kwargs):
        raise LookupError("missing")

    monkeypatch.setattr(market_impact.market_impact_agent, "assess", missing)
    assert client.post("/api/market-impact/assessment", json={"line": "G60", "feature": "seats"}).status_code == 404
