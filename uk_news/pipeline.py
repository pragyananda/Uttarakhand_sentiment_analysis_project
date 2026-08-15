"""Orchestration: discover -> dedupe -> hydrate -> tag -> store."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import discovery, extract
from .models import Article
from .net import PoliteSession
from .relevance import Tagger
from .storage import Store

log = logging.getLogger(__name__)

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def load_config(config_dir: Path | str = CONFIG_DIR) -> tuple[dict, dict]:
    config_dir = Path(config_dir)
    with open(config_dir / "sources.yaml", encoding="utf-8") as fh:
        sources = yaml.safe_load(fh)
    with open(config_dir / "keywords.yaml", encoding="utf-8") as fh:
        keywords = yaml.safe_load(fh)
    return sources, keywords


@dataclass
class RunReport:
    discovered: int = 0
    after_dedupe: int = 0
    already_stored: int = 0
    bodies_ok: int = 0
    bodies_failed: int = 0
    dropped_irrelevant: int = 0
    inserted: int = 0
    skipped_duplicate: int = 0
    per_source: dict[str, int] = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            "",
            "=" * 58,
            "  SCRAPE REPORT",
            "=" * 58,
            f"  discovered from feeds : {self.discovered}",
            f"  after URL dedupe      : {self.after_dedupe}",
            f"  already in database   : {self.already_stored}",
            f"  full text extracted   : {self.bodies_ok}",
            f"  body failed (kept as  : {self.bodies_failed}",
            "   title+summary only)",
            f"  dropped as off-topic  : {self.dropped_irrelevant}",
            "-" * 58,
            f"  NEW rows inserted     : {self.inserted}",
            f"  duplicates skipped    : {self.skipped_duplicate}",
            "=" * 58,
        ]
        if self.per_source:
            lines.append("  new rows by source:")
            for name, n in sorted(self.per_source.items(), key=lambda kv: -kv[1]):
                lines.append(f"    {name:<32s} {n}")
            lines.append("=" * 58)
        return "\n".join(lines)


def run_query(
    keyword: str,
    days: int = 7,
    lang: str = "hi",
    limit: int = 20,
    db_path: str = "data/articles.db",
    config_dir: Path | str = CONFIG_DIR,
    include_rss: bool = False,
    government_only: bool = True,
    fetch_bodies: bool = True,
    workers: int = 4,
    on_progress=None,
) -> tuple[RunReport, list[Article]]:
    """Scrape on demand for one keyword/hashtag over a date window.

    This is what the dashboard's Scrape button calls. Returns the report plus
    the articles kept, so the UI can show them immediately.

    `days` becomes Google News' `when:Nd` operator — the date window is applied
    at the source, not filtered afterwards, so we don't fetch a month of
    articles to keep three days of them.
    """
    sources_cfg, keywords_cfg = load_config(config_dir)
    defaults = sources_cfg.get("defaults", {})
    report = RunReport()

    session = PoliteSession(
        user_agent=defaults.get("user_agent", "UK-SentimentBot/1.0"),
        per_domain_delay=float(defaults.get("per_domain_delay", 1.5)),
        timeout=int(defaults.get("request_timeout", 25)),
        max_retries=int(defaults.get("max_retries", 2)),
        respect_robots=bool(defaults.get("respect_robots", True)),
    )
    tagger = Tagger(keywords_cfg)
    store = Store(db_path)
    known = store.known_urls()

    term = (keyword or "").strip().lstrip("#")
    query = f"{term} when:{max(1, int(days))}d" if term else f"उत्तराखंड when:{days}d"

    if on_progress:
        on_progress(f"searching Google News: {query}")

    found: list[Article] = []
    trusted: set[str] = set()
    try:
        found.extend(discovery.from_gnews(
            {"name": f"query:{term or 'uttarakhand'}", "q": query, "lang": lang},
            limit=limit, known=known))
    except Exception as exc:
        log.error("query discovery failed: %s", exc)

    if include_rss:
        for src in sources_cfg.get("rss_sources") or []:
            if not src.get("enabled"):
                continue
            trusted.add(src["name"])
            try:
                found.extend(discovery.from_rss(src, session=session,
                                                limit=limit))
            except Exception as exc:
                log.error("[%s] %s", src.get("name"), exc)

    report.discovered = len(found)
    unique = discovery.dedupe(found)
    report.after_dedupe = len(unique)
    fresh = [a for a in unique if a.canonical_url not in known]
    report.already_stored = len(unique) - len(fresh)

    if fetch_bodies and fresh:
        if on_progress:
            on_progress(f"fetching {len(fresh)} article bodies…")

        def _hydrate(art: Article) -> bool:
            try:
                return extract.hydrate(art, session)
            except Exception:
                return False

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ok in pool.map(_hydrate, fresh):
                report.bodies_ok += ok
                report.bodies_failed += (not ok)

    keep: list[Article] = []
    for art in fresh:
        if not tagger.tag(art, trusted_source=art.source_name in trusted):
            report.dropped_irrelevant += 1
            continue
        # The UI's "Uttarakhand Government only" switch. Applied after tagging
        # so the article's own text is searched, not just its headline.
        if government_only:
            blob = f"{art.title}\n{art.summary}\n{art.text}"
            if not tagger.is_government_related(blob):
                report.dropped_irrelevant += 1
                continue
        keep.append(art)

    if on_progress:
        on_progress(f"scoring sentiment for {len(keep)} articles…")

    # Score immediately so the new rows aren't blank in the dashboard.
    if keep:
        try:
            from .sentiment import SentimentScorer
            scorer = SentimentScorer()
            texts = [scorer._prep(a.title, a.text or a.summary) for a in keep]
            for art, (label, score) in zip(keep, scorer.score_texts(texts)):
                art.sentiment_label, art.sentiment_score = label, score
        except Exception as exc:
            log.warning("sentiment scoring skipped: %s", exc)

    inserted, skipped = store.save_many(keep)
    report.inserted, report.skipped_duplicate = inserted, skipped
    for art in keep:
        report.per_source[art.source_name] = \
            report.per_source.get(art.source_name, 0) + 1

    # save_many ignores unknown columns, so write the scores explicitly.
    for art in keep:
        if getattr(art, "sentiment_label", None):
            store.conn.execute(
                "UPDATE articles SET sentiment_label=?, sentiment_score=? "
                "WHERE id=?", (art.sentiment_label, art.sentiment_score, art.id))
    store.conn.commit()
    store.close()
    return report, keep


def run(
    db_path: str = "data/articles.db",
    config_dir: Path | str = CONFIG_DIR,
    limit_per_source: int | None = None,
    gnews_limit: int = 25,
    workers: int = 4,
    skip_gnews: bool = False,
    fetch_bodies: bool = True,
) -> RunReport:
    sources_cfg, keywords_cfg = load_config(config_dir)
    defaults = sources_cfg.get("defaults", {})
    report = RunReport()

    session = PoliteSession(
        user_agent=defaults.get("user_agent", "UK-SentimentBot/1.0"),
        per_domain_delay=float(defaults.get("per_domain_delay", 1.5)),
        timeout=int(defaults.get("request_timeout", 25)),
        max_retries=int(defaults.get("max_retries", 2)),
        respect_robots=bool(defaults.get("respect_robots", True)),
    )
    tagger = Tagger(keywords_cfg)
    store = Store(db_path)
    known = store.known_urls()
    log.info("database holds %d articles", len(known))

    # --- 1. discovery ----------------------------------------------------
    found: list[Article] = []
    trusted: set[str] = set()      # source names that bypass the relevance gate

    for src in sources_cfg.get("rss_sources") or []:
        if not src.get("enabled"):
            continue
        trusted.add(src["name"])
        try:
            found.extend(discovery.from_rss(src, session=session,
                                            limit=limit_per_source))
        except Exception as exc:
            log.error("[%s] discovery failed: %s", src.get("name"), exc)

    if not skip_gnews:
        for q in sources_cfg.get("gnews_queries") or []:
            if not q.get("enabled"):
                continue
            try:
                found.extend(discovery.from_gnews(
                    q, limit=gnews_limit, known=known))
            except Exception as exc:
                log.error("[%s] gnews failed: %s", q.get("name"), exc)

    report.discovered = len(found)

    # --- 2. dedupe, and drop what we already hold ------------------------
    unique = discovery.dedupe(found)
    report.after_dedupe = len(unique)
    fresh = [a for a in unique if a.canonical_url not in known]
    report.already_stored = len(unique) - len(fresh)
    log.info("%d discovered -> %d unique -> %d new",
             report.discovered, report.after_dedupe, len(fresh))

    # --- 3. hydrate bodies ------------------------------------------------
    if fetch_bodies and fresh:
        log.info("fetching %d article bodies (%d workers)…", len(fresh), workers)

        def _hydrate(art: Article) -> bool:
            try:
                return extract.hydrate(art, session)
            except Exception as exc:
                log.debug("hydrate error %s: %s", art.url, exc)
                return False

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ok in pool.map(_hydrate, fresh):
                if ok:
                    report.bodies_ok += 1
                else:
                    report.bodies_failed += 1

    # --- 4. tag + relevance gate -----------------------------------------
    keep: list[Article] = []
    for art in fresh:
        if tagger.tag(art, trusted_source=art.source_name in trusted):
            keep.append(art)
        else:
            report.dropped_irrelevant += 1

    # --- 5. store ---------------------------------------------------------
    inserted, skipped = store.save_many(keep)
    report.inserted, report.skipped_duplicate = inserted, skipped
    for art in keep:
        report.per_source[art.source_name] = \
            report.per_source.get(art.source_name, 0) + 1

    store.close()
    return report
