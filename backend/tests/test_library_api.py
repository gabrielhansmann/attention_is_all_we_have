"""Evidence library endpoints. Read-only, so they run against the real database; mocked variants cover errors."""
import pytest
from fastapi.testclient import TestClient

from app.api import library as library_api
from app.main import app

client = TestClient(app)


def test_sources_lists_every_loaded_file_with_what_came_from_it(db):
    r = client.get("/api/sources")
    assert r.status_code == 200
    by_file = {s["file"]: s for s in r.json()}
    assert {"G60_feedback_hackathon.xlsx", "G60_OptionList.PDF", "sales_volumes.xlsx"} <= set(by_file)
    assert by_file["G60_feedback_hackathon.xlsx"]["family"] == "Customer feedback"
    assert by_file["G60_feedback_hackathon.xlsx"]["counts"]["feedback"] == 5005
    assert by_file["G60_OptionList.PDF"]["family"] == "Product catalog"
    assert by_file["G60_OptionList.PDF"]["counts"]["pdf_chunks"] > 0 and by_file["G60_OptionList.PDF"]["counts"]["options"] > 0
    assert by_file["sales_volumes.xlsx"]["family"] == "Sales volumes"
    assert by_file["sales_volumes.xlsx"]["counts"]["sales_rows"] == 36


def test_coverage_shows_real_gaps_not_just_totals(db):
    body = client.get("/api/evidence/coverage").json()
    cells = {(c["line"], c["market"]): c for c in body["cells"]}
    assert len(cells) == 16                                    # 4 lines x 4 markets, gaps included
    assert all(cells[(l, "CN")]["feedback"] == 0 for l in ("F70", "G60", "G68", "G70"))   # no China feedback exists
    assert cells[("G60", "US")]["feedback"] > cells[("G60", "EU")]["feedback"] > 0
    assert cells[("G68", "CN")]["sales_2025"] == 75000 and cells[("G60", "CN")]["sales_2025"] is None
    assert cells[("F70", "US")]["sales_2025"] == 0             # a recorded zero is not the same as no row
    assert sum(c["feedback"] for c in body["cells"]) <= body["total_feedback"] == 13771
    assert body["options_by_line"]["G60"] == 62


@pytest.mark.parametrize("path", ["/api/sources", "/api/evidence/coverage"])
def test_outages_are_503_without_details(path, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("password=secret host=db.example")
    monkeypatch.setattr(library_api.library, "list_sources", boom)
    monkeypatch.setattr(library_api.library, "coverage", boom)
    r = client.get(path)
    assert r.status_code == 503 and "secret" not in r.text and "db.example" not in r.text
