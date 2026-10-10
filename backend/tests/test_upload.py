"""Uploading a source file: layout detection, the endpoint's refusals, and a real load that is rolled back."""
import io
import os
import shutil
from types import SimpleNamespace

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.api import library as library_api
from app.api.deps import get_ingest_conn
from app.ingest import upload
from app.main import app

client = TestClient(app)

FEEDBACK_HEADER = ["ID", "Source", "Brand", "Sales description", "Country", "Derivate", "Engine", "Type", "Comment",
                   "VFC", "VFC level 2", "VFC level 3"]


def xlsx(sheets: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for r in rows:
            ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def feedback_file(n=3) -> bytes:
    rows = [[f"T-{i}", "Source A", "[BMW]", "[BMW 5 Series]", "US" if i else "XX", "G60", "BEVE", "Likes",
             f"upload test comment {i}", "x", "x", None] for i in range(n)]
    return xlsx({"Feedback_Explorer": [FEEDBACK_HEADER, *rows, [None, None, None, None, "US"]]})


SALES = xlsx({"G60_G68": [["Market", "Code", "2024", "2025", "2030 (forecast)"],
                          ["China", "CN", 10, 20, 30], ["Europe", "EU", 1, 2, "n/a"]]})


def tiny_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with selectable text, written by hand so the test needs no PDF library."""
    text = "BT /F1 11 Tf 50 780 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(text)} >>\nstream\n{text}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    return out + f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()


class FakeEmbeddings:
    def create(self, model, input):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1536) for _ in input])


FAKE_OPENAI = SimpleNamespace(embeddings=FakeEmbeddings())


@pytest.mark.parametrize("data,kind", [
    (feedback_file(), "feedback"),
    (SALES, "sales"),
    (xlsx({"CN_EU_2025": [["x"]], "US_2025": [["x"]]}), "studies"),
    (xlsx({"Sheet1": [["a", "b"], [1, 2]]}), None),
])
def test_a_spreadsheet_is_recognised_by_its_layout(tmp_path, data, kind):
    path = tmp_path / "anything.xlsx"
    path.write_bytes(data)
    assert upload.excel_kind(path) == kind


# ---------------------------------------------------------------- endpoint, no database

@pytest.fixture
def no_conn():
    app.dependency_overrides[get_ingest_conn] = lambda: None
    yield
    app.dependency_overrides.pop(get_ingest_conn, None)


def test_the_endpoint_hands_the_file_to_the_loader_and_reports_what_was_stored(no_conn, monkeypatch):
    seen = {}

    def fake(conn, filename, data, *, line, replace):
        seen.update(filename=filename, data=data, line=line, replace=replace)
        return {"file": filename, "kind": "sales", "replaced": True, "notes": ["1 cells skipped"],
                "counts": {"feedback": 0, "pdf_chunks": 0, "options": 0, "study_cells": 0, "sales_rows": 5}}
    monkeypatch.setattr(library_api.upload, "ingest_upload", fake)
    r = client.post("/api/sources", params={"filename": "more_sales.xlsx", "line": "G60", "replace": "true"}, content=b"PK-bytes")
    assert r.status_code == 201 and r.json()["counts"]["sales_rows"] == 5 and r.json()["replaced"] is True
    assert seen == {"filename": "more_sales.xlsx", "data": b"PK-bytes", "line": "G60", "replace": True}


def test_empty_and_oversized_files_are_refused_before_loading(no_conn, monkeypatch):
    monkeypatch.setattr(library_api.upload, "ingest_upload", lambda *a, **k: pytest.fail("must not load"))
    assert client.post("/api/sources", params={"filename": "a.pdf"}, content=b"").status_code == 422
    monkeypatch.setattr(library_api.upload, "MAX_BYTES", 10)
    r = client.post("/api/sources", params={"filename": "a.pdf"}, content=b"%PDF" + b"x" * 20)
    assert r.status_code == 413 and "too large" in r.json()["detail"]


def test_loader_refusals_keep_their_status_and_outages_hide_details(no_conn, monkeypatch):
    def refuse(*a, **k):
        raise upload.AlreadyLoaded("a.pdf is already loaded.")
    monkeypatch.setattr(library_api.upload, "ingest_upload", refuse)
    r = client.post("/api/sources", params={"filename": "a.pdf"}, content=b"%PDF")
    assert r.status_code == 409 and r.json()["detail"] == "a.pdf is already loaded."

    def boom(*a, **k):
        raise RuntimeError("password=secret host=db.example")
    monkeypatch.setattr(library_api.upload, "ingest_upload", boom)
    r = client.post("/api/sources", params={"filename": "a.pdf"}, content=b"%PDF")
    assert r.status_code == 503 and "secret" not in r.text


class NoQueries:
    def execute(self, *a, **k):
        pytest.fail("a refused file must not reach the database")


@pytest.mark.parametrize("name,data,message", [
    ("notes.docx", b"PK", "Only PDF and Excel"),
    ("fake.pdf", b"PK\x03\x04", "does not match its extension"),
    ("fake.xlsx", b"%PDF-1.7", "does not match its extension"),
    ("../", b"%PDF", "needs a name"),
])
def test_wrong_file_types_are_refused_without_touching_the_database(name, data, message):
    with pytest.raises(upload.UploadError, match=message):
        upload.ingest_upload(NoQueries(), name, data)


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


def test_a_feedback_upload_is_stored_normalized_and_refused_a_second_time(conn):
    out = upload.ingest_upload(conn, "C:\\tmp\\upload_test_feedback.xlsx", feedback_file(), line="G60", client=FAKE_OPENAI)
    assert out["file"] == "upload_test_feedback.xlsx" and out["kind"] == "feedback" and out["replaced"] is False
    assert out["counts"]["feedback"] == 3
    assert any("1 rows skipped" in n for n in out["notes"]) and any("1 comments have a country" in n for n in out["notes"])
    rows = conn.execute(
        "select f.vehicle_line, f.market_code, f.polarity, f.powertrain, f.embedding is not null, s.vehicle_line "
        "from public.feedback_raw f join public.source s on s.id = f.source_id where s.uri = %s order by f.row_no",
        ("upload_test_feedback.xlsx",)).fetchall()
    assert rows == [("G60", None, "positive", "BEV", True, "G60"), ("G60", "US", "positive", "BEV", True, "G60"),
                    ("G60", "US", "positive", "BEV", True, "G60")]

    with pytest.raises(upload.AlreadyLoaded):
        upload.ingest_upload(conn, "upload_test_feedback.xlsx", feedback_file(), client=FAKE_OPENAI)
    again = upload.ingest_upload(conn, "upload_test_feedback.xlsx", feedback_file(2), replace=True, client=FAKE_OPENAI)
    assert again["replaced"] is True and again["counts"]["feedback"] == 2
    assert conn.execute("select count(*) from public.feedback_raw f join public.source s on s.id = f.source_id "
                        "where s.uri = 'upload_test_feedback.xlsx'").fetchone()[0] == 2


def test_a_sales_upload_reads_years_from_the_header_and_splits_the_shared_sheet(conn):
    out = upload.ingest_upload(conn, "upload_test_sales.xlsx", SALES)
    assert out["kind"] == "sales" and out["counts"]["sales_rows"] == 5 and any("1 cells skipped" in n for n in out["notes"])
    rows = conn.execute(
        "select v.market_code, v.year, v.volume, v.is_forecast, v.vehicle_line from public.sales_volume v "
        "join public.source s on s.id = v.source_id where s.uri = 'upload_test_sales.xlsx' order by 1, 2").fetchall()
    assert rows == [("CN", 2024, 10, False, "G68"), ("CN", 2025, 20, False, "G68"), ("CN", 2030, 30, True, "G68"),
                    ("EU", 2024, 1, False, "G60"), ("EU", 2025, 2, False, "G60")]


def test_an_unknown_layout_or_vehicle_line_stores_nothing(conn):
    with pytest.raises(upload.UploadError, match="layout was not recognised"):
        upload.ingest_upload(conn, "upload_test_other.xlsx", xlsx({"Sheet1": [["a", "b"], [1, 2]]}))
    with pytest.raises(upload.UploadError, match="Unknown vehicle line"):
        upload.ingest_upload(conn, "upload_test_other.xlsx", SALES, line="E39")
    assert conn.execute("select count(*) from public.source where uri = 'upload_test_other.xlsx'").fetchone()[0] == 0


@pytest.mark.skipif(not shutil.which("pdftotext"), reason="poppler is not installed")
def test_a_pdf_upload_becomes_cited_text_passages(conn):
    pdf = tiny_pdf(["DEALER REPORT SPRING", "Customers ask for a larger boot and a quieter cabin at motorway speed.",
                    "Several mention the head-up display as a reason to choose the car."])
    out = upload.ingest_upload(conn, "upload_test_report.pdf", pdf, line="G60", client=FAKE_OPENAI)
    assert out["kind"] == "pdf" and out["counts"]["pdf_chunks"] == 1 and out["counts"]["options"] == 0
    rows = conn.execute(
        "select c.page, c.locator, c.heading, c.content, c.embedding is not null, s.type, s.vehicle_line "
        "from public.chunk c join public.source s on s.id = c.source_id where s.uri = 'upload_test_report.pdf'").fetchall()
    assert len(rows) == 1
    page, locator, heading, content, embedded, type_, line = rows[0]
    assert (page, locator, heading, embedded, type_, line) == (1, "p.1", "DEALER REPORT SPRING", True, "internal_pdf", "G60")
    assert "quieter cabin at motorway speed" in content

    with pytest.raises(upload.UploadError, match="No selectable text"):
        upload.ingest_upload(conn, "upload_test_blank.pdf", tiny_pdf([]), client=FAKE_OPENAI)


def test_options_are_stored_with_a_model_variant_per_availability_mark(conn):
    from app.ingest.load_excel import source_id
    from app.ingest.load_options import powertrain, store_options
    from app.ingest.pdf_options import Entry, Option

    assert [powertrain(v) for v in ("i5 eDrive40", "iX1 xDrive30", "530e", "520d xDrive")] == ["BEV", "BEV", "PHEV", "ICE"]
    sid = source_id(conn, "upload_test_catalog.pdf", "G60", type="internal_pdf")
    option = Option(page=7, section="ASSISTENZ", code="ZZ9", name="Test option",
                    entries=[Entry(["upload test i5", "520i"], ["standard", "optional"], 500.0, 420.17, None)])
    assert store_options(conn, sid, "G60", [option]) == 2
    assert store_options(conn, sid, "G60", [option]) == 2          # loading again replaces, it does not add
    rows = conn.execute(
        "select a.variant, a.status, v.vehicle_line, v.powertrain from public.option o "
        "join public.option_availability a on a.option_id = o.id join public.model_variant v on v.id = a.variant_id "
        "where o.source_id = %s order by 1", (sid,)).fetchall()
    assert rows == [("520i", "optional", "G60", "ICE"), ("upload test i5", "standard", "G60", "ICE")]
