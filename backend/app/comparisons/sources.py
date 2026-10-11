"""Keep technical table cells readable and follow publisher-hosted data sheets."""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

from app.ingest import load_web as web
from app.ingest.upload import UploadError


class TechnicalHTML(web._Text):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ('td', 'th') and not self._skip:
            self._buf.append(' ')
        if tag == 'a' and not self._skip:
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)
        super().handle_starttag(tag, attrs)


def technical_links(url: str, links: list[str]) -> list[str]:
    """Only PDF links actually in the page and hosted by that publisher are followed."""
    host=(urlsplit(url).hostname or '').removeprefix('www.')
    result=[]
    for href in links:
        try:
            target=web.normalize_url(urljoin(url,href))
        except UploadError:
            continue
        parts=urlsplit(target)
        target_host=(parts.hostname or '').removeprefix('www.')
        if not parts.path.lower().endswith('.pdf') or not (target_host==host or target_host.endswith('.'+host)):
            continue
        if target not in result:result.append(target)
    return sorted(result,key=lambda u:(not bool(re.search(r'techn|spec|daten|TD-',u,re.I)),u))[:6]


def extract_html(url: str, kind: str, raw: bytes):
    text=raw.decode('utf-8',errors='replace')
    if kind=='text/plain':
        title,blocks=web.extract(kind,text)
        return title,web.passages(title or url,blocks),[]
    parser=TechnicalHTML()
    parser.feed(text)
    parser.close()
    return parser.title,web.passages(parser.title or url,parser.blocks),technical_links(url,parser.links)


def source_priority(url: str) -> tuple:
    path=urlsplit(url).path.lower()
    return (not path.endswith('.pdf'), not bool(re.search(r'techn|spec|daten',path)), bool(re.search(r'configurator|/buy/|/shop/',path)),url)
