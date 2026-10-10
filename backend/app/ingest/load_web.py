"""Fetch one web page a PM added and store it as cited text passages, like a PDF.

  URL -> source (type 'web', uri = the URL, trust tier, optional vehicle line and market)
         + chunk (one row per passage, embedded, so Evidence search and the agents find it)

Only the page behind the URL is read: no crawling, no JavaScript, no login. The text is what the page serves as
HTML with scripts, navigation and forms left out. A passage is numbered in reading order and that number is
stored as the chunk's `page`, so a website is cited as "page N" the way a catalog is.
The connection must be in autocommit mode (or inside a transaction the caller ends), as in the loader scripts.

The address is checked before every request, redirects included: only http(s) to a public address is fetched,
so the endpoint cannot be used to read services inside the network the backend runs in.
"""
from __future__ import annotations

import ipaddress
import re
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import psycopg
from openai import OpenAI, OpenAIError

from app.ingest.load_pdfs import embed_chunks, vec
from app.ingest.upload import AlreadyLoaded, InUse, Unavailable, UploadError

MAX_BYTES = 3 * 1024 * 1024
MAX_URL = 2000
MAX_REDIRECTS = 5
TIMEOUT = 15
MAX_CHARS = 1800       # as for PDF chunks
MIN_CHARS = 40
SMALL_CHUNK = 250      # a passage shorter than this is joined to the next one under the same heading
MAX_PASSAGES = 150
TRUST_TIERS = ("oem", "trade_press", "forum_social")
USER_AGENT = "BMW-Product-Intelligence/0.1 (evidence ingestion)"

SKIP = {"script", "style", "noscript", "template", "svg", "nav", "footer", "header", "aside", "form", "button",
        "select", "iframe", "figure"}
BLOCK = {"p", "div", "li", "tr", "br", "section", "article", "blockquote", "pre", "table", "ul", "ol", "dd", "dt",
         "h4", "h5", "h6", "main"}
HEADINGS = {"h1", "h2", "h3"}
VOID = {"br", "img", "input", "meta", "link", "hr", "source", "wbr", "area", "base", "col", "embed", "track"}


@dataclass
class Passage:
    title: str
    page: int              # position of the passage on the page, from 1
    heading: str | None
    text: str

    @property
    def locator(self) -> str:
        return f"passage {self.page}"

    @property
    def embed_input(self) -> str:
        head = self.title + (f" — {self.heading}" if self.heading else "")
        return f"{head}\n{self.text}"


# ---------------------------------------------------------------- address

def normalize_url(url: str) -> str:
    """The URL as it is stored: scheme and host in lower case, no fragment. Refuses anything but http(s)."""
    url = (url or "").strip()
    if len(url) > MAX_URL:
        raise UploadError("The address is too long.")
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        raise UploadError("Enter a full web address that starts with https:// or http://.")
    if parts.username or parts.password:
        raise UploadError("An address with a user name or password in it cannot be added.")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))


def check_public(url: str) -> None:
    """Refuse an address that does not resolve to a public one (loopback, private ranges, link-local, metadata)."""
    host = urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        raise UploadError(f"The address {host} could not be found.")
    if not infos or not all(ipaddress.ip_address(info[4][0].split("%")[0]).is_global for info in infos):
        raise UploadError("Only pages on the public internet can be added.")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _tls() -> ssl.SSLContext:
    """Certificates are verified against certifi's bundle (installed with the OpenAI client): a python.org
    build of Python on macOS has no system certificates, and every https page would fail."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch_page(url: str) -> tuple[str, str]:
    """(content type, text) of the page. Follows redirects one at a time so each address is checked."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_tls()))
    for _ in range(MAX_REDIRECTS + 1):
        check_public(url)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain;q=0.8"})
        try:
            with opener.open(req, timeout=TIMEOUT) as res:
                kind = res.headers.get_content_type()
                if kind not in ("text/html", "application/xhtml+xml", "text/plain"):
                    raise UploadError(f"The address returns {kind}, not a web page. Upload files in the Files tab.")
                raw = res.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise UploadError(f"The page is larger than {MAX_BYTES // 2**20} MB.")
                return kind, raw.decode(res.headers.get_content_charset() or "utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            target = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
            if target:
                url = normalize_url(urljoin(url, target))
                continue
            if e.code in (401, 403):
                raise UploadError(f"The site refused the request ({e.code}). Pages behind a login or a bot check cannot be added.")
            raise UploadError(f"The site answered with an error ({e.code}).")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            raise UploadError("The page could not be reached.")
    raise UploadError("The address redirects too many times.")


# ---------------------------------------------------------------- text

class _Text(HTMLParser):
    """Visible text as (heading, paragraph) pairs in reading order, without scripts, navigation or forms."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.blocks: list[tuple[str | None, str]] = []
        self._heading: str | None = None
        self._buf: list[str] = []
        self._skip = 0
        self._in: str | None = None      # "title" or a heading tag while inside one

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        self._buf = []
        if not text:
            return
        if self._in == "title":
            self.title = text
        elif self._in in HEADINGS:
            self._heading = text
        else:
            self.blocks.append((self._heading, text))

    def handle_starttag(self, tag, attrs):
        if tag in VOID and tag != "br":
            return
        if tag in SKIP:
            self._skip += 1
        elif self._skip:
            return
        elif tag == "title" or tag in HEADINGS:
            self._flush()
            self._in = tag
        elif tag in BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in SKIP:
            self._skip = max(0, self._skip - 1)
        elif self._skip:
            return
        elif tag == self._in:
            self._flush()
            self._in = None
        elif tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self._skip:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def extract(kind: str, text: str) -> tuple[str, list[tuple[str | None, str]]]:
    """(page title, blocks). Plain text is split on blank lines."""
    if kind == "text/plain":
        return "", [(None, re.sub(r"\s+", " ", b).strip()) for b in re.split(r"\n\s*\n", text) if b.strip()]
    parser = _Text()
    parser.feed(text)
    parser.close()
    return parser.title, parser.blocks


def passages(title: str, blocks: list[tuple[str | None, str]]) -> list[Passage]:
    """Blocks under one heading are joined up to MAX_CHARS; a long block is cut at a sentence end."""
    out: list[Passage] = []
    heading: str | None = None
    buf: list[str] = []

    def flush():
        nonlocal buf
        text = "\n".join(buf).strip()
        buf = []
        if len(text) >= MIN_CHARS:
            out.append(Passage(title, len(out) + 1, heading, text))

    for block_heading, text in blocks:
        if block_heading != heading:
            flush()
            heading = block_heading
        while len(text) > MAX_CHARS:
            cut = text.rfind(". ", 0, MAX_CHARS)
            if cut < MAX_CHARS // 2:
                cut = text.rfind(" ", 0, MAX_CHARS)
            cut = cut + 1 if cut > 0 else MAX_CHARS
            flush()
            buf = [text[:cut].strip()]
            flush()
            text = text[cut:].strip()
        if sum(len(b) + 1 for b in buf) + len(text) > MAX_CHARS and sum(len(b) for b in buf) >= SMALL_CHUNK:
            flush()
        buf.append(text)
    flush()
    return out


# ---------------------------------------------------------------- store

def default_tier(url: str) -> str:
    """The trust tier the web agents would give this site, used when the PM does not choose one."""
    from app.agents.market_trend_agent import SourceDoc, infer_trust_tier
    return infer_trust_tier(SourceDoc(url=url, title=url, snippet="", retrieved_at=""))


def store_page(conn, url: str, title: str, line: str | None, market: str | None, tier: str,
               chunks: list[Passage], embeddings: list[list[float]]):
    """Register the page as a source and replace its passages. Returns the source id."""
    with conn.transaction():
        row = conn.execute("select id from public.source where uri = %s", (url,)).fetchone()
        if row:
            sid = row[0]
            conn.execute("update public.source set type = 'web', vehicle_line = %s, market = %s, trust_tier = %s, "
                         "title = %s, retrieved_at = now() where id = %s", (line, market, tier, title, sid))
        else:
            sid = conn.execute(
                "insert into public.source (type, uri, vehicle_line, market, trust_tier, title) "
                "values ('web', %s, %s, %s, %s, %s) returning id", (url, line, market, tier, title)).fetchone()[0]
        conn.execute("delete from public.chunk where source_id = %s", (sid,))
        for c, e in zip(chunks, embeddings):
            conn.execute(
                "insert into public.chunk (source_id, locator, heading, content, embedding, page, chunk_index) "
                "values (%s, %s, %s, %s, %s::extensions.vector, %s, 0)",
                (sid, c.locator, c.heading, c.text, vec(e), c.page))
    return sid


def ingest_website(conn: psycopg.Connection, url: str, *, line: str | None = None, market: str | None = None,
                   trust_tier: str | None = None, replace: bool = False, client=None, fetch=fetch_page) -> dict:
    """Fetch and store one page. Returns what was loaded: {file, kind, replaced, counts, notes}."""
    url = normalize_url(url)
    if trust_tier and trust_tier not in TRUST_TIERS:
        raise UploadError(f"Unknown trust tier: {trust_tier}.")
    for kind, key, label in (("vehicle_line", line, "vehicle line"), ("market", market, "market")):
        if key and not conn.execute("select 1 from public.ontology where kind = %s and key = %s", (kind, key)).fetchone():
            raise UploadError(f"Unknown {label}: {key}.")
    replaced = conn.execute("select 1 from public.source where uri = %s", (url,)).fetchone() is not None
    if replaced and not replace:
        raise AlreadyLoaded("This page is already stored. Add it again as a replacement to fetch it anew.")

    content_type, text = fetch(url)
    title, blocks = extract(content_type, text)
    chunks = passages(title or urlsplit(url).hostname or url, blocks)
    if not chunks:
        raise UploadError("No readable text was found. Pages that build their content with JavaScript are not supported.")
    notes: list[str] = []
    if len(chunks) > MAX_PASSAGES:
        notes.append(f"The page is long: the first {MAX_PASSAGES} of {len(chunks)} passages were stored.")
        chunks = chunks[:MAX_PASSAGES]
    try:
        embeddings = embed_chunks(client if client is not None else OpenAI(), chunks)
        store_page(conn, url, chunks[0].title, line, market, trust_tier or default_tier(url), chunks, embeddings)
    except OpenAIError:
        raise Unavailable("The embedding service is unavailable, so nothing was stored.")
    except psycopg.errors.ForeignKeyViolation:
        raise InUse("Findings already cite passages of this page, so it cannot be replaced.")
    counts = {"feedback": 0, "pdf_chunks": len(chunks), "options": 0, "study_cells": 0, "sales_rows": 0}
    return {"file": url, "kind": "web", "replaced": replaced, "counts": counts, "notes": notes}


def remove_website(conn: psycopg.Connection, source_id: str) -> None:
    """Delete a stored web page and its passages. Files are not removed this way. Raises LookupError or InUse."""
    row = conn.execute("select type from public.source where id = %s", (source_id,)).fetchone()
    if not row or row[0] != "web":
        raise LookupError("no such website")
    try:
        with conn.transaction():
            conn.execute("delete from public.chunk where source_id = %s", (source_id,))
            conn.execute("delete from public.source where id = %s", (source_id,))
    except psycopg.errors.ForeignKeyViolation:
        raise InUse("Findings cite this page, so it cannot be removed.")
