"""Article schema shared across discovery, extraction and storage.

The field set is deliberately shaped for what Phase 2/3 need downstream
(normalisation -> sentiment -> dashboard), not just for what RSS gives us.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Tracking params that change per-referrer but point at the same article.
# Stripping these is what makes deduplication actually work.
_TRACKING_PARAMS = re.compile(
    r"^(utm_|fbclid|gclid|igshid|mc_cid|mc_eid|ref|referrer|source|amp_|_ga)",
    re.I,
)


def canonicalize_url(url: str) -> str:
    """Strip tracking noise so the same article yields one stable key.

    Google News, Facebook shares and the publishers' own newsletters all
    decorate URLs differently; without this we'd store the same story 3-4 times
    and skew every sentiment count built on top.
    """
    if not url:
        return ""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()

    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=False)
        if not _TRACKING_PARAMS.match(k)
    ]
    netloc = parts.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    if netloc.startswith("m."):
        netloc = netloc[2:]

    path = parts.path.rstrip("/") or "/"
    # Drop AMP suffixes so /article/amp and /article collapse together.
    path = re.sub(r"/amp$", "", path, flags=re.I)

    return urlunsplit((parts.scheme.lower() or "https", netloc, path,
                       urlencode(query), ""))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Article:
    """One scraped news item.

    `id` is derived from the canonical URL, so re-running the scraper is
    idempotent: the same story never lands twice.
    """

    url: str
    source_name: str = ""
    publisher: str = ""
    discovery: str = "rss"          # rss | gnews
    title: str = ""
    summary: str = ""               # RSS description — useful even if body fails
    text: str = ""                  # full article body
    language: str = ""              # hi | en | unknown
    published_at: Optional[str] = None   # ISO8601, publisher's timestamp
    scraped_at: str = field(default_factory=_now_iso)

    # Enrichment for Phase 3 (NER + aspect-based sentiment)
    districts: list[str] = field(default_factory=list)
    aspects: list[str] = field(default_factory=list)
    matched_keywords: list[str] = field(default_factory=list)

    image_url: str = ""             # og:image — the article's lead photo
    extractor: str = ""             # which extractor won: trafilatura|newspaper4k
    word_count: int = 0
    canonical_url: str = ""
    id: str = ""

    def __post_init__(self) -> None:
        self.canonical_url = canonicalize_url(self.url)
        if not self.id:
            self.id = hashlib.sha1(
                self.canonical_url.encode("utf-8")).hexdigest()
        if not self.word_count:
            self.word_count = len(self.text.split()) if self.text else 0

    @property
    def best_text(self) -> str:
        """Body if we got one, else the RSS summary.

        Headlines + summaries still carry usable sentiment signal, so a failed
        body extraction should degrade the record, not discard it.
        """
        return self.text or self.summary or self.title

    def to_row(self) -> dict:
        d = asdict(self)
        for k in ("districts", "aspects", "matched_keywords"):
            d[k] = "|".join(d[k])
        return d


ARTICLE_COLUMNS = [
    "id", "url", "canonical_url", "source_name", "publisher", "discovery",
    "title", "summary", "text", "language", "published_at", "scraped_at",
    "districts", "aspects", "matched_keywords", "image_url", "extractor",
    "word_count",
]
