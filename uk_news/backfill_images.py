"""Backfill `image_url` for articles stored before image extraction existed.

    python -m uk_news.backfill_images

Re-fetches each article page and pulls its og:image. Safe to re-run: it only
touches rows where image_url is still empty.
"""

from __future__ import annotations

import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor

from .extract import extract_image
from .net import PoliteSession
from .pipeline import load_config

log = logging.getLogger(__name__)


def backfill(db_path: str = "data/articles.db", workers: int = 6,
             progress=None) -> tuple[int, int]:
    sources_cfg, _ = load_config()
    defaults = sources_cfg.get("defaults", {})
    session = PoliteSession(
        user_agent=defaults.get("user_agent", "UK-SentimentBot/1.0"),
        # Lower than the scraper's delay: this is a one-off metadata sweep of
        # pages we have already fetched once, and it is spread across ~35 hosts.
        per_domain_delay=1.0,
        timeout=int(defaults.get("request_timeout", 25)),
        max_retries=1,
        respect_robots=bool(defaults.get("respect_robots", True)),
    )

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = list(conn.execute(
        "SELECT id, url FROM articles "
        "WHERE image_url IS NULL OR image_url = ''"))
    if not rows:
        conn.close()
        return 0, 0

    log.info("backfilling images for %d articles", len(rows))
    done = [0]

    def fetch(row):
        html = session.get_text(row["url"])
        img = extract_image(html, row["url"]) if html else ""
        done[0] += 1
        if progress and done[0] % 20 == 0:
            progress(done[0], len(rows))
        return row["id"], img

    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, rows))

    found = [(img, aid) for aid, img in results if img]
    conn.executemany("UPDATE articles SET image_url=? WHERE id=?", found)
    conn.commit()
    conn.close()
    return len(found), len(rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def _p(d, t):
        print(f"  {d}/{t}", flush=True)

    got, total = backfill(progress=_p)
    print(f"found images for {got} of {total} articles")
