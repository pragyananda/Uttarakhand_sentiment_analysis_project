"""Full-text extraction with a fallback chain.

Measured on live Uttarakhand articles (2026-08-14):

    URL                          trafilatura   newspaper4k
    amarujala/boulder-falls...        1437         1970
    amarujala/cm-dhami...            1287         1879
    news18/pithoragarh...          0 or 2560       n/a
    hillmail/chamoli-tunnel...       2813          n/a

Neither library wins everywhere and trafilatura intermittently returned 0 on
the same URL across runs, so we try both and keep the longer result. Writing
per-site CSS parsers was rejected: six-plus outlets, all liable to redesign.

newspaper4k needs `indic-nlp-library` or it raises ImportError on any Hindi
page — it auto-detects language, so you cannot dodge this by omitting the
language argument.
"""

from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

MIN_BODY_CHARS = 200      # below this it's a stub/paywall, not an article


def _with_trafilatura(html: str, url: str) -> tuple[str, Optional[str]]:
    try:
        import trafilatura
    except ImportError:
        return "", None
    try:
        text = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        ) or ""
        date = None
        try:
            meta = trafilatura.extract_metadata(html)
            date = meta.date if meta else None
        except Exception:
            pass
        return text.strip(), date
    except Exception as exc:
        log.debug("trafilatura failed on %s: %s", url, exc)
        return "", None


def _with_newspaper(html: str, url: str) -> tuple[str, Optional[str]]:
    try:
        import newspaper
    except ImportError:
        return "", None
    try:
        art = newspaper.Article(url)
        art.download(input_html=html)
        art.parse()
        date = art.publish_date.date().isoformat() if art.publish_date else None
        return (art.text or "").strip(), date
    except Exception as exc:
        log.debug("newspaper4k failed on %s: %s", url, exc)
        return "", None


# XPath rather than CSS selectors so lxml alone is enough — .cssselect()
# needs the extra `cssselect` package, which isn't worth a dependency here.
_IMAGE_XPATHS = (
    "//meta[@property='og:image']/@content",
    "//meta[@name='og:image']/@content",
    "//meta[@property='og:image:url']/@content",
    "//meta[@name='twitter:image']/@content",
    "//meta[@name='twitter:image:src']/@content",
    "//link[@rel='image_src']/@href",
)


def extract_image(html: str, url: str) -> str:
    """Pull the article's lead photo from social-card metadata.

    og:image is the most reliable image on an Indian news page — the <img>
    tags in the body are frequently lazy-loaded placeholders or ad slots,
    whereas og:image is what the publisher wants shown when the story is
    shared, so it is the real lead photo.
    """
    if not html:
        return ""
    try:
        from lxml import html as lhtml
        from urllib.parse import urljoin
        doc = lhtml.fromstring(html)
        for xpath in _IMAGE_XPATHS:
            for src in doc.xpath(xpath):
                src = (src or "").strip()
                if src and not src.startswith("data:"):
                    return urljoin(url, src)
    except Exception as exc:
        log.debug("image extraction failed on %s: %s", url, exc)
    return ""


def extract_body(html: str, url: str) -> tuple[str, str, Optional[str]]:
    """Return (text, extractor_name, published_date_or_None).

    Runs both extractors and keeps whichever produced more text.
    """
    if not html:
        return "", "", None

    t_text, t_date = _with_trafilatura(html, url)
    n_text, n_date = _with_newspaper(html, url)

    if len(n_text) > len(t_text):
        return n_text, "newspaper4k", (n_date or t_date)
    if t_text:
        return t_text, "trafilatura", (t_date or n_date)
    return "", "", (t_date or n_date)


def hydrate(article, session) -> bool:
    """Fetch and fill in an Article's body in place.

    Returns True if a usable body was stored. A False return is not fatal:
    the RSS title+summary still carries sentiment signal (see
    `Article.best_text`), so the caller keeps the record either way.
    """
    html = session.get_text(article.url)
    if not html:
        return False

    if not article.image_url:
        article.image_url = extract_image(html, article.url)

    text, extractor, date = extract_body(html, article.url)
    if len(text) >= MIN_BODY_CHARS:
        article.text = text
        article.extractor = extractor
        article.word_count = len(text.split())
    if not article.published_at and date:
        article.published_at = date
    return bool(article.text)
