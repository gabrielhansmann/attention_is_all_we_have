"""Extract text per page from the catalog PDFs and split it into citable chunks.

Every chunk keeps the file name, page number and its exact text, so an answer can quote the
real PDF. Needs `pdftotext` (poppler) on PATH.
"""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MAX_CHARS = 1800
MIN_CHARS = 40
SMALL_CHUNK = 250   # chunks shorter than this are merged into a neighbour on the same page
HEADING_RE = re.compile(r"^[A-ZÄÖÜ0-9][A-ZÄÖÜ0-9 &/,\-–\.\*]{5,70}$")


@dataclass
class Chunk:
    file: str
    title: str
    page: int
    index: int          # position of the chunk within the page
    heading: str | None
    text: str           # normalised page text, verbatim otherwise: this is the quotable citation

    @property
    def locator(self) -> str:
        return f"p.{self.page}"

    @property
    def embed_input(self) -> str:
        head = f"{self.title} — Seite {self.page}"
        if self.heading:
            head += f" — {self.heading}"
        return f"{head}\n{self.text}"


def _pdf_title(path: Path) -> str:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("Title:"):
            return line.split(":", 1)[1].strip() or path.stem
    return path.stem


def _page_count(path: Path) -> int:
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, check=True).stdout
    return int(next(l for l in out.splitlines() if l.startswith("Pages:")).split(":")[1])


def _page_lines(path: Path, page: int) -> list[str]:
    raw = subprocess.run(
        ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(path), "-"],
        capture_output=True, text=True, check=True,
    ).stdout
    lines = [re.sub(r"[ \t­]+", " ", l).strip() for l in raw.splitlines()]
    return [l for l in lines if l]


def chunk_pdf(path: Path) -> list[Chunk]:
    title = _pdf_title(path)
    chunks: list[Chunk] = []
    for page in range(1, _page_count(path) + 1):
        lines = _page_lines(path, page)
        if sum(len(l) for l in lines) < MIN_CHARS:
            continue
        heading, buf, size, idx = None, [], 0, 0

        def flush():
            nonlocal buf, size, idx
            text = "\n".join(buf).strip()
            if len(text) >= MIN_CHARS:
                chunks.append(Chunk(path.name, title, page, idx, heading, text))
                idx += 1
            buf, size = [], 0

        for line in lines:
            if HEADING_RE.match(line) and len(line) > 5:
                flush()
                heading = line.rstrip(".")
            if size + len(line) > MAX_CHARS and buf:
                flush()
            buf.append(line)
            size += len(line) + 1
        flush()
    return _merge_small(chunks)


def _merge_small(chunks: list[Chunk]) -> list[Chunk]:
    """Fold fragments (often a table cut mid-way) into the previous chunk on the same page,
    or into the next one when they open the page. The text stays verbatim, so citations hold."""
    merged: list[Chunk] = []
    carry: Chunk | None = None
    for c in chunks:
        if carry is not None:
            if carry.page == c.page:
                c = Chunk(c.file, c.title, c.page, carry.index, carry.heading or c.heading,
                          carry.text + "\n" + c.text)
            else:
                merged.append(carry)
            carry = None
        if len(c.text) < SMALL_CHUNK:
            if merged and merged[-1].page == c.page:
                prev = merged[-1]
                merged[-1] = Chunk(prev.file, prev.title, prev.page, prev.index, prev.heading,
                                   prev.text + "\n" + c.text)
            else:
                carry = c
            continue
        merged.append(c)
    if carry is not None:
        merged.append(carry)
    # re-number positions within each page
    seen: dict[int, int] = {}
    for c in merged:
        c.index = seen.get(c.page, 0)
        seen[c.page] = c.index + 1
    return merged


if __name__ == "__main__":
    import sys
    for p in sys.argv[1:]:
        cs = chunk_pdf(Path(p))
        print(p, len(cs), "chunks; avg", sum(len(c.text) for c in cs) // max(len(cs), 1), "chars")
