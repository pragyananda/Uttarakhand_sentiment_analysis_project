"""SQLite persistence with URL-level deduplication.

SQLite (not Postgres) because the project doc calls for a prototype store and
this keeps the repo runnable with zero services. The schema is plain enough to
port to Postgres later by swapping the connection.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Iterable

from .models import Article, ARTICLE_COLUMNS

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id            TEXT PRIMARY KEY,
    url           TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    source_name   TEXT,
    publisher     TEXT,
    discovery     TEXT,
    title         TEXT,
    summary       TEXT,
    text          TEXT,
    language      TEXT,
    published_at  TEXT,
    scraped_at    TEXT,
    districts     TEXT,
    aspects       TEXT,
    matched_keywords TEXT,
    image_url     TEXT,
    extractor     TEXT,
    word_count    INTEGER,
    -- Phase 3 writes here; the scraper only ever leaves them NULL.
    sentiment_label TEXT,
    sentiment_score REAL
);
CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_articles_source    ON articles(source_name);
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_canonical
    ON articles(canonical_url);
"""


class Store:
    def __init__(self, path: str | Path = "data/articles.db"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        """Add columns introduced after a database was first created.

        CREATE TABLE IF NOT EXISTS silently skips an existing table, so new
        columns would never appear on a store built by an earlier version.
        """
        have = {r[1] for r in self.conn.execute("PRAGMA table_info(articles)")}
        for col, decl in (("image_url", "TEXT"),
                          ("sentiment_label", "TEXT"),
                          ("sentiment_score", "REAL")):
            if col not in have:
                self.conn.execute(
                    f"ALTER TABLE articles ADD COLUMN {col} {decl}")

    # -- writes ------------------------------------------------------------
    def save_many(self, articles: Iterable[Article]) -> tuple[int, int]:
        """Insert articles, skipping ones we already hold.

        Returns (inserted, skipped_as_duplicate).
        """
        inserted = skipped = 0
        cols = ", ".join(ARTICLE_COLUMNS)
        ph = ", ".join("?" for _ in ARTICLE_COLUMNS)
        sql = f"INSERT OR IGNORE INTO articles ({cols}) VALUES ({ph})"

        for art in articles:
            row = art.to_row()
            cur = self.conn.execute(sql, [row[c] for c in ARTICLE_COLUMNS])
            if cur.rowcount:
                inserted += 1
            else:
                skipped += 1
        self.conn.commit()
        return inserted, skipped

    def known_urls(self) -> set[str]:
        """Canonical URLs already stored — lets discovery skip re-fetching."""
        return {r[0] for r in
                self.conn.execute("SELECT canonical_url FROM articles")}

    # -- reads -------------------------------------------------------------
    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def stats(self) -> list[sqlite3.Row]:
        return list(self.conn.execute(
            """SELECT source_name, publisher, COUNT(*) AS n,
                      SUM(CASE WHEN text != '' THEN 1 ELSE 0 END) AS with_body,
                      MIN(published_at) AS oldest, MAX(published_at) AS newest
               FROM articles GROUP BY source_name ORDER BY n DESC"""))

    def aspect_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for (blob,) in self.conn.execute(
                "SELECT aspects FROM articles WHERE aspects != ''"):
            for a in blob.split("|"):
                counts[a] = counts.get(a, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])

    # -- exports for the Phase 3 / Phase 4 hand-off ------------------------
    def export_csv(self, path: str | Path) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(self.conn.execute(
            f"SELECT {', '.join(ARTICLE_COLUMNS)} FROM articles "
            "ORDER BY published_at DESC"))
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(ARTICLE_COLUMNS)
            w.writerows(rows)
        return len(rows)

    def export_jsonl(self, path: str | Path) -> int:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = list(self.conn.execute(
            f"SELECT {', '.join(ARTICLE_COLUMNS)} FROM articles "
            "ORDER BY published_at DESC"))
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                d = dict(zip(ARTICLE_COLUMNS, r))
                for k in ("districts", "aspects", "matched_keywords"):
                    d[k] = d[k].split("|") if d[k] else []
                fh.write(json.dumps(d, ensure_ascii=False) + "\n")
        return len(rows)

    def close(self) -> None:
        self.conn.close()
