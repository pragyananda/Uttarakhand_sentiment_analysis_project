"""Turn configured sources into a de-duplicated list of article URLs.

Two paths:
  * direct publisher RSS  -> feedparser, links are already real
  * Google News RSS search -> links are encoded `news.google.com/rss/articles/CBM...`
    redirectors that do NOT resolve via HTTP redirect (verified: they return
    200 on the Google URL itself). They must be decoded through Google's
    internal batchexecute endpoint, which `googlenewsdecoder` implements.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, Optional
from urllib.parse import quote

import feedparser

from .models import Article, canonicalize_url

log = logging.getLogger(__name__)

GNEWS_ENDPOINT = "https://news.google.com/rss/search"


def _parse_date(entry) -> Optional[str]:
    """Normalise whatever date form the feed used into ISO8601 UTC."""
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            try:
                return datetime(*tm[:6], tzinfo=timezone.utc).isoformat(
                    timespec="seconds")
            except (TypeError, ValueError):
                pass
    return None


def _clean_summary(entry) -> str:
    """RSS summaries are HTML fragments; reduce to plain text."""
    raw = entry.get("summary", "") or entry.get("description", "")
    if not raw:
        return ""
    try:
        from lxml import html as lhtml
        return lhtml.fromstring(raw).text_content().strip()
    except Exception:
        import re
        return re.sub(r"<[^>]+>", " ", raw).strip()


def from_rss(source: dict, session=None, limit: Optional[int] = None
             ) -> list[Article]:
    """Read one publisher RSS feed into Article stubs (no body text yet)."""
    url = source["url"]
    name = source.get("name", url)

    # Fetch through the polite session when available so rate limiting and
    # robots handling apply to feeds too, not just article pages.
    raw = session.get_text(url) if session else None
    parsed = feedparser.parse(raw if raw is not None else url)

    if getattr(parsed, "bozo", 0) and not parsed.entries:
        log.warning("[%s] feed unparseable: %s", name,
                    getattr(parsed, "bozo_exception", "unknown"))
        return []

    out: list[Article] = []
    for entry in parsed.entries[: limit or len(parsed.entries)]:
        link = entry.get("link")
        if not link:
            continue
        out.append(Article(
            url=link,
            source_name=name,
            publisher=source.get("publisher", ""),
            discovery="rss",
            title=(entry.get("title") or "").strip(),
            summary=_clean_summary(entry),
            language=source.get("language", ""),
            published_at=_parse_date(entry),
        ))
    log.info("[%s] %d items from RSS", name, len(out))
    return out


def _decode_gnews_link(link: str) -> Optional[str]:
    """Recover the publisher URL behind a Google News redirector."""
    try:
        from googlenewsdecoder import gnewsdecoder
    except ImportError:
        log.error("googlenewsdecoder not installed — Google News sources "
                  "will be skipped. pip install googlenewsdecoder")
        return None
    try:
        res = gnewsdecoder(link, interval=1)
        if res.get("status") and res.get("decoded_url"):
            return res["decoded_url"]
        log.debug("decode failed: %s", res.get("message"))
    except Exception as exc:
        log.debug("decode error %s: %s", type(exc).__name__, exc)
    return None


def from_gnews(query: dict, limit: Optional[int] = None,
               known: Optional[set[str]] = None) -> list[Article]:
    """Run one Google News search and decode results to publisher URLs.

    Decoding costs ~1s per link (Google rate-limits), so `known` is used to
    skip decoding anything we can already rule out, and `limit` caps the work.
    """
    lang = query.get("lang", "hi")
    hl, ceid = (("hi-IN", "IN:hi") if lang == "hi" else ("en-IN", "IN:en"))
    feed_url = (f"{GNEWS_ENDPOINT}?q={quote(query['q'])}"
                f"&hl={hl}&gl=IN&ceid={ceid}")
    name = query.get("name", query["q"][:30])

    parsed = feedparser.parse(feed_url)
    entries = parsed.entries[: limit or len(parsed.entries)]
    log.info("[%s] %d results from Google News, decoding…", name, len(entries))

    out: list[Article] = []
    failed = 0
    for entry in entries:
        gl = entry.get("link")
        if not gl:
            continue
        real = _decode_gnews_link(gl)
        if not real:
            failed += 1
            continue
        if known and canonicalize_url(real) in known:
            continue

        # Google appends " - Publisher" to titles; the source tag is cleaner.
        publisher = ""
        src = entry.get("source")
        if src:
            publisher = getattr(src, "title", "") or src.get("title", "")
        title = (entry.get("title") or "").strip()
        if publisher and title.endswith(f" - {publisher}"):
            title = title[: -len(f" - {publisher}")]

        out.append(Article(
            url=real,
            source_name=name,
            publisher=publisher,
            discovery="gnews",
            title=title,
            summary=_clean_summary(entry),
            language=lang,
            published_at=_parse_date(entry),
        ))

    if failed:
        log.warning("[%s] %d/%d links failed to decode", name, failed,
                    len(entries))
    log.info("[%s] %d usable articles", name, len(out))
    return out


def dedupe(articles: Iterable[Article]) -> list[Article]:
    """Collapse articles sharing a canonical URL, keeping the richest copy.

    The state and district feeds of the same publisher overlap heavily, and
    Google News surfaces stories we already pulled directly.
    """
    best: dict[str, Article] = {}
    for art in articles:
        prev = best.get(art.id)
        if prev is None:
            best[art.id] = art
            continue
        # Prefer the record carrying more usable signal, then prefer direct
        # RSS over gnews since its metadata is first-party.
        if (len(art.best_text), art.discovery == "rss") > \
           (len(prev.best_text), prev.discovery == "rss"):
            best[art.id] = art
    return list(best.values())
