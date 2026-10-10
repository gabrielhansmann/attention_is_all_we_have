"""Turn one uploaded file into evidence rows, with the same loaders that read the provided files.

  PDF                   -> source + chunk (searchable text, cited by page); option + option_availability too
                           when the equipment tables are found and a vehicle line is given
  feedback export .xlsx -> feedback_raw (comments embedded, normalized to line / market / domain / polarity)
  sales volumes .xlsx   -> sales_volume
  customer study .xlsx  -> study_response

A spreadsheet is recognised by its layout, not its name. The file name is the source's identity: uploading a
name that is already loaded is refused unless `replace` is set, and then replaces that file's rows.
The connection must be in autocommit mode (or inside a transaction the caller ends), as in the loader scripts.
"""
from __future__ import annotations

import subprocess
import tempfile
import zipfile
from pathlib import Path

import openpyxl
import psycopg
from openai import OpenAI, OpenAIError

from app.ingest import load_excel
from app.ingest.load_options import store_options
from app.ingest.load_pdfs import embed_chunks, store_chunks
from app.ingest.pdf_chunks import chunk_pdf
from app.ingest.pdf_options import parse_pdf

MAX_BYTES = 25 * 1024 * 1024
MARKET_CODES = {"EU", "CN", "US", "RoW"}
LAYOUTS = ("Supported spreadsheets: the feedback export (12 columns, one comment per row), sales volumes "
           "(one sheet per vehicle line) and the customer study cross-tabs.")


class UploadError(Exception):
    """Something the person uploading can act on; the message is shown to them."""
    status = 422


class AlreadyLoaded(UploadError):
    status = 409


class InUse(UploadError):
    status = 409


class Unavailable(UploadError):
    status = 503


def clean_name(filename: str) -> str:
    name = Path(filename.replace("\\", "/")).name.strip()
    if not name or name.startswith("."):
        raise UploadError("The file needs a name.")
    return name


def excel_kind(path: Path) -> str | None:
    """feedback | sales | studies, from the sheet names and the first rows; None when the layout is unknown."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheets = wb.worksheets
        if not sheets:
            return None
        if any(ws.title.startswith(("CN_EU", "US_")) for ws in sheets):
            return "studies"
        head = [tuple(r) for r in sheets[0].iter_rows(min_row=1, max_row=6, values_only=True)]
    finally:
        wb.close()
    if len(head) < 2:
        return None
    rows = head[1:]
    if any(len(r) >= 3 and load_excel.txt(r[1]) in MARKET_CODES and isinstance(r[2], (int, float)) for r in rows):
        return "sales"
    width = sum(1 for v in head[0] if load_excel.txt(v))
    if width >= load_excel.FEEDBACK_COLS and any(load_excel.txt(r[0]) for r in rows if r):
        return "feedback"
    return None


def _pdf(conn, path: Path, line: str | None, client, notes: list[str]) -> dict:
    try:
        chunks = chunk_pdf(path)
    except FileNotFoundError:
        raise Unavailable("PDF upload needs poppler (pdftotext) on the server.")
    except (subprocess.CalledProcessError, StopIteration, ValueError):
        raise UploadError("The PDF could not be read.")
    if not chunks:
        raise UploadError("No selectable text was found in the PDF. Scanned documents are not supported.")
    try:
        options = parse_pdf(path)
    except Exception:          # the table parser is written for one catalog layout; any other PDF is still text
        options = []
        notes.append("The equipment tables could not be parsed. The text is stored.")
    embeddings = embed_chunks(client(), chunks)

    n_avail = 0
    with conn.transaction():
        sid = store_chunks(conn, path.name, line, chunks, embeddings)
        conn.execute("delete from public.option where source_id = %s", (sid,))
        if options and not line:
            notes.append(f"{len(options)} equipment options were found but not stored: choose a vehicle line.")
            options = []
        elif options:
            n_avail = store_options(conn, sid, line, options)
    if n_avail:
        notes.append(f"{n_avail} availability marks (standard or optional per model variant) stored.")
    return {"pdf_chunks": len(chunks), "options": len(options)}


def _excel(conn, path: Path, line: str | None, client, notes: list[str]) -> tuple[str, dict]:
    try:
        kind = excel_kind(path)
        if kind is None:
            raise UploadError(f"The spreadsheet layout was not recognised. {LAYOUTS}")
        if kind == "feedback":
            n, skipped = load_excel.ingest_feedback(conn, client(), path, line)
            unmapped = conn.execute(
                "select count(*) from public.feedback_raw f join public.source s on s.id = f.source_id "
                "where s.uri = %s and f.market_code is null", (path.name,)).fetchone()[0]
            if skipped:
                notes.append(f"{skipped} rows skipped: no ID in the first column.")
            if unmapped:
                notes.append(f"{unmapped} comments have a country that maps to no market, so market filters miss them.")
            return kind, {"feedback": n}
        if kind == "sales":
            n, skipped = load_excel.ingest_sales(conn, path)
            if skipped:
                notes.append(f"{skipped} cells skipped: no market code or no number.")
            return kind, {"sales_rows": n}
        n, skipped = load_excel.ingest_studies(conn, path)
        if skipped:
            notes.append(f"{skipped} cells skipped: no market, model or question.")
        return kind, {"study_cells": n}
    except load_excel.LayoutError as e:
        raise UploadError(f"Nothing could be read from the spreadsheet ({e}). {LAYOUTS}")
    except (zipfile.BadZipFile, KeyError, IndexError, openpyxl.utils.exceptions.InvalidFileException):
        raise UploadError("The spreadsheet could not be read.")


def ingest_upload(conn: psycopg.Connection, filename: str, data: bytes, *, line: str | None = None,
                  replace: bool = False, client=None) -> dict:
    """Store one file. Returns what was loaded: {file, kind, replaced, counts, notes}."""
    name = clean_name(filename)
    ext = Path(name).suffix.lower()
    if ext not in (".pdf", ".xlsx"):
        raise UploadError("Only PDF and Excel (.xlsx) files can be uploaded.")
    if not data.startswith(b"%PDF" if ext == ".pdf" else b"PK"):
        raise UploadError("The file content does not match its extension.")
    if line and not conn.execute(
            "select 1 from public.ontology where kind = 'vehicle_line' and key = %s", (line,)).fetchone():
        raise UploadError(f"Unknown vehicle line: {line}.")
    replaced = conn.execute("select 1 from public.source where uri = %s", (name,)).fetchone() is not None
    if replaced and not replace:
        raise AlreadyLoaded(f"{name} is already loaded. Upload it again as a replacement to overwrite its rows.")

    get_client = (lambda: client) if client is not None else OpenAI
    notes: list[str] = []
    counts = {"feedback": 0, "pdf_chunks": 0, "options": 0, "study_cells": 0, "sales_rows": 0}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / name
        path.write_bytes(data)
        try:
            if ext == ".pdf":
                kind = "pdf"
                counts.update(_pdf(conn, path, line, get_client, notes))
            else:
                kind, loaded = _excel(conn, path, line, get_client, notes)
                counts.update(loaded)
        except OpenAIError:
            raise Unavailable("The embedding service is unavailable, so nothing was stored.")
        except psycopg.errors.ForeignKeyViolation:
            raise InUse(f"Findings already cite rows of {name}, so it cannot be replaced. Upload under another name.")
    return {"file": name, "kind": kind, "replaced": replaced, "counts": counts, "notes": notes}
