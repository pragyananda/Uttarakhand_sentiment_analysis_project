"""Command line entry point.

    python -m uk_news scrape --limit 10
    python -m uk_news scrape --skip-gnews          # fast, direct feeds only
    python -m uk_news stats
    python -m uk_news export --format csv
    python -m uk_news check                        # probe feed health
"""

from __future__ import annotations

import argparse
import logging
import sys

from .pipeline import run, load_config, CONFIG_DIR
from .storage import Store


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    # These are noisy at DEBUG and drown out our own output.
    for noisy in ("urllib3", "trafilatura", "newspaper", "charset_normalizer"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def cmd_scrape(args) -> int:
    report = run(
        db_path=args.db,
        limit_per_source=args.limit,
        gnews_limit=args.gnews_limit,
        workers=args.workers,
        skip_gnews=args.skip_gnews,
        fetch_bodies=not args.no_bodies,
    )
    print(report.render())
    return 0


def cmd_stats(args) -> int:
    store = Store(args.db)
    total = store.count()
    print(f"\n  {total} articles in {args.db}\n")
    if total:
        print(f"  {'source':<32s} {'n':>5s} {'body':>6s}  newest")
        print("  " + "-" * 62)
        for r in store.stats():
            print(f"  {r['source_name']:<32s} {r['n']:>5d} "
                  f"{r['with_body']:>6d}  {(r['newest'] or '')[:10]}")
        print("\n  aspect distribution:")
        for aspect, n in store.aspect_counts():
            bar = "#" * min(40, n)
            print(f"    {aspect:<24s} {n:>5d}  {bar}")
    store.close()
    return 0


def cmd_export(args) -> int:
    store = Store(args.db)
    if args.format in ("csv", "both"):
        n = store.export_csv(args.out_csv)
        print(f"  wrote {n} rows -> {args.out_csv}")
    if args.format in ("jsonl", "both"):
        n = store.export_jsonl(args.out_jsonl)
        print(f"  wrote {n} rows -> {args.out_jsonl}")
    store.close()
    return 0


def cmd_check(args) -> int:
    """Probe every configured feed so dead sources surface immediately."""
    import feedparser
    sources_cfg, _ = load_config(CONFIG_DIR)
    print("\n  feed health check\n  " + "-" * 60)
    bad = 0
    for src in sources_cfg.get("rss_sources") or []:
        if not src.get("enabled"):
            print(f"  SKIP  {src['name']:<34s} (disabled: "
                  f"{src.get('reason', 'no reason given')[:40]})")
            continue
        parsed = feedparser.parse(src["url"])
        n = len(parsed.entries)
        status = "OK  " if n else "DEAD"
        if not n:
            bad += 1
        print(f"  {status}  {src['name']:<34s} {n:>4d} items")
    print("  " + "-" * 60)
    print(f"  {bad} enabled feed(s) returned nothing\n")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="uk_news",
        description="Uttarakhand newspaper scraper "
                    "(Phase 1 ingestion for the sentiment analysis project)")
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--db", default="data/articles.db")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scrape", help="discover + fetch + store articles")
    s.add_argument("--limit", type=int, default=None,
                   help="max items per RSS feed (default: all)")
    s.add_argument("--gnews-limit", type=int, default=25,
                   help="max results per Google News query (default 25); "
                        "decoding costs ~1s each, so keep this modest")
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--skip-gnews", action="store_true",
                   help="direct publisher feeds only — much faster")
    s.add_argument("--no-bodies", action="store_true",
                   help="headlines + summaries only, skip article fetch")
    s.set_defaults(func=cmd_scrape)

    st = sub.add_parser("stats", help="what is in the database")
    st.set_defaults(func=cmd_stats)

    e = sub.add_parser("export", help="dump to csv/jsonl for Phase 2/3")
    e.add_argument("--format", choices=["csv", "jsonl", "both"], default="both")
    e.add_argument("--out-csv", default="data/articles.csv")
    e.add_argument("--out-jsonl", default="data/articles.jsonl")
    e.set_defaults(func=cmd_export)

    c = sub.add_parser("check", help="probe configured feeds for liveness")
    c.set_defaults(func=cmd_check)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n  interrupted — partial results are already committed")
        return 130


if __name__ == "__main__":
    sys.exit(main())
