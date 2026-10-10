"""Tier 1: parse the equipment tables of the catalog PDFs into options with per-variant availability.

The tables put the SA code at a fixed x position, the gross price next to it, the net price in
brackets on the following line, and one ■ (standard) / □ (optional) mark per model variant at a
fixed x position. The variant names are printed rotated by 90 degrees in the page header; they are
decoded and matched to the marks by x position, which is what makes the availability reliable.

Rules worth knowing:
- An option can have several price lines (different price per variant group); each is an entry.
- Code-only options directly below a priced one (e.g. paint colours) share its price and marks;
  these entries are flagged `inherited`.
"""
import collections
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

CODE_RE = re.compile(r"^[0-9A-Z]{3,4}$")
PRICE_RE = re.compile(r"^(\d{1,3}(?:\.\d{3})*,–|–,–)$")
NET_RE = re.compile(r"^\[(\d{1,3}(?:\.\d{3})*,\d{2})\]$")
HEADING_RE = re.compile(r"^[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9 &/,\-–\.\*]{2,70}$")
MARK_MIN_X = 300       # legend marks sit left of this; variant marks right of it
LINE_TOL = 4.2


@dataclass
class Entry:
    variants: list[str]
    status: list[str]          # parallel to variants: standard | optional
    price_gross: float | None
    price_net: float | None
    condition: str | None
    inherited: bool = False


@dataclass
class Option:
    page: int
    section: str | None
    code: str
    name: str
    description: str = ""
    entries: list[Entry] = field(default_factory=list)


def _num(s: str) -> float:
    s = s.replace(",–", ",00").replace(".", "").replace(",", ".")
    return float(s)


def _header_x(words, text):
    """x position of a rotated header label such as 'SA-Nr.' (printed reversed)."""
    w = next((w for w in words if not w["upright"] and w["text"][::-1] == text), None)
    return w["x0"] if w else None


def _variant_columns(words, mark_xs):
    """Decode the rotated header words into one variant name per mark column."""
    cols = collections.defaultdict(list)
    for w in words:
        if w["upright"] or w["x0"] < mark_xs[0] - 12:
            continue
        x = min(mark_xs, key=lambda m: abs(m - w["x0"]))
        if abs(x - w["x0"]) <= 12:
            cols[x].append(w)
    return {x: " ".join(w["text"][::-1] for w in sorted(ws, key=lambda w: -w["top"])) for x, ws in cols.items()}


def _lines(words):
    out, cur, top = [], [], None
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if top is None or abs(w["top"] - top) <= LINE_TOL:
            cur.append(w)
            top = w["top"] if top is None else top
        else:
            out.append(cur)
            cur, top = [w], w["top"]
    if cur:
        out.append(cur)
    return [sorted(l, key=lambda w: w["x0"]) for l in out]


def parse_pdf(path: Path) -> list[Option]:
    options: list[Option] = []
    last_variants: dict[float, str] = {}
    last_sa = last_inkl = None
    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            marks = [c for c in page.chars if c["text"] in "■□" and c["x0"] > MARK_MIN_X]
            if not marks:
                continue
            mark_xs = sorted({round(c["x0"]) for c in marks})
            words = page.extract_words(extra_attrs=["upright"])
            variants = _variant_columns(words, mark_xs) or last_variants
            last_variants = variants
            sa_x = _header_x(words, "SA-Nr.") or last_sa
            inkl_x = _header_x(words, "inkl.") or last_inkl
            if sa_x is None or inkl_x is None:
                continue                      # a page of selected standard equipment: no SA codes
            last_sa, last_inkl = sa_x, inkl_x
            code_x = (sa_x - 10, sa_x + 8)
            price_x = (inkl_x - 8, mark_xs[0] - 12)
            legend_top = min((c["top"] for c in page.chars if c["text"] in "■□" and c["x0"] < 60), default=9999)
            body = [w for w in words if w["upright"] and 115 < w["top"] < legend_top - 1]
            section, cur, group_entries, last_price_entry = None, None, [], None
            prev_top = None
            for line in _lines(body):
                top = line[0]["top"]
                left = [w for w in line if w["x1"] < code_x[0] + 8 and w["x0"] < code_x[0]]
                text = " ".join(w["text"] for w in left)
                code_w = next((w for w in line if code_x[0] <= w["x0"] <= code_x[1] and CODE_RE.match(w["text"])), None)
                price_w = next((w for w in line if price_x[0] <= w["x0"] <= price_x[1] and PRICE_RE.match(w["text"])), None)
                net_w = next((w for w in line if price_x[0] - 10 <= w["x0"] <= price_x[1] and NET_RE.match(w["text"])), None)
                line_marks = [w for w in line if w["text"] in ("■", "□") and w["x0"] > MARK_MIN_X]

                if net_w and last_price_entry and top - last_price_entry[1] <= 14 and last_price_entry[0].price_net is None:
                    last_price_entry[0].price_net = _num(NET_RE.match(net_w["text"]).group(1))
                if text and not code_w and not price_w and not line_marks and not net_w \
                        and HEADING_RE.match(text) and left[0]["x0"] < 60:
                    section, cur, group_entries = text.rstrip("."), None, []
                    prev_top = top
                    continue
                if code_w:
                    cur = Option(pno, section, code_w["text"], text)
                    options.append(cur)
                elif text and cur is not None and (prev_top is None or top - prev_top < 30):
                    if not (price_w or line_marks):
                        cur.description = (cur.description + " " + text).strip()
                if line_marks and cur is not None:
                    xs = [min(mark_xs, key=lambda m: abs(m - w["x0"])) for w in line_marks]
                    price = price_w["text"] if price_w else None
                    entry = Entry(
                        variants=[variants.get(x, f"col@{x}") for x in xs],
                        status=["standard" if w["text"] == "■" else "optional" for w in line_marks],
                        price_gross=None if price in (None, "–,–") else _num(price),
                        price_net=None,
                        condition=text if (text and not code_w and cur.entries) else None,
                    )
                    cur.entries.append(entry)
                    group_entries = [e for e in cur.entries]
                    last_price_entry = (entry, top)
                elif code_w and cur is not None and not cur.entries and group_entries:
                    cur.entries = [Entry(e.variants, e.status, e.price_gross, e.price_net, e.condition, True)
                                   for e in group_entries]
                prev_top = top
    return options


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        opts = parse_pdf(Path(p))
        with_e = sum(1 for o in opts if o.entries)
        print(f"{p}: {len(opts)} options, {with_e} with availability, "
              f"{sum(1 for o in opts if o.entries and o.entries[0].inherited)} inherited")
