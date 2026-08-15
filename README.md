# Uttarakhand Newspaper Scraper

**Phase 1 ingestion layer — "Local News Portals"** for the *Public Sentiment &
Opinion Mining System: Uttarakhand Government Focus* prototype
(Milestone 2, Weeks 2–3).

Collects Uttarakhand news articles from regional outlets, extracts full article
text (Hindi + English), tags each article with **district** and **aspect**
labels, deduplicates, and stores everything in SQLite ready for the Phase 2
normalisation and Phase 3 sentiment stages.

---

## Quick start

```bash
pip install -r requirements.txt

python -m uk_news check                     # are the feeds alive?
python -m uk_news scrape --limit 20         # collect
python -m uk_news.sentiment                 # score sentiment (Hindi + English)
python -m uk_news stats                     # what did we get
python -m uk_news export --format both      # data/articles.csv + .jsonl

streamlit run app.py                        # the dashboard
```

Useful flags:

| Flag                | Effect                                                                               |
| ------------------- | ------------------------------------------------------------------------------------ |
| `--skip-gnews`    | Direct publisher feeds only. Much faster — Google News decoding costs ~1s per link. |
| `--limit N`       | Cap items per RSS feed.                                                              |
| `--gnews-limit N` | Cap results per Google News query (default 25).                                      |
| `--no-bodies`     | Headlines + summaries only; skips article page fetches.                              |
| `-v`              | Debug logging.                                                                       |

Re-running is safe: articles are keyed by canonical URL, so nothing duplicates.
Run it on a schedule (cron/`systemd` timer) to build the time series the
**Sentiment Timeline** in Phase 4 needs.

---

## Sources

Every enabled feed was probed live on **2026-08-14** and returned parseable items.

**Direct RSS** (preferred — fast, first-party metadata):

| Source                      | Lang | Items                               |
| --------------------------- | ---- | ----------------------------------- |
| Amar Ujala — Uttarakhand   | hi   | 40                                  |
| Amar Ujala — Dehradun      | hi   | 40 (only 21 overlap the state feed) |
| News18 Hindi — Uttarakhand | hi   | 200                                 |
| Garhwal Post                | en   | 10                                  |
| Hill Mail                   | hi   | 10                                  |
| Devbhoomi Media             | hi   | 10                                  |

**Google News RSS search** — recovers publishers that have no usable feed, plus
topical queries for the grievances in the project doc §2 (UKSSSC/paper leak,
youth unemployment, protests).

### Sources that do NOT work (verified, don't retry)

| Publisher                  | Why                                                                |
| -------------------------- | ------------------------------------------------------------------ |
| Dainik Jagran              | HTTP 404 on all four URL patterns — public RSS appears retired    |
| Live Hindustan             | HTTP 503 — bot-blocked at the edge                                |
| TOI Dehradun / HT Dehradun | Return 200 but**0 items**; generic feeds carry national news |
| ETV Bharat                 | HTTP 404                                                           |

All four are still reachable **through Google News**, which is the main reason
that path exists. Decoding was confirmed resolving to `jagran.com`,
`bhaskar.com` and `etvbharat.com`.

---

## How it works

```
sources.yaml
    │
    ├── RSS feeds ──────────► feedparser ──┐
    │                                      │
    └── Google News search ─► feedparser ──┤
                              + URL decode │
                                           ▼
                                    dedupe by canonical URL
                                           │
                                           ▼
                              fetch page (polite session)
                                           │
                                           ▼
                       extract body: trafilatura + newspaper4k
                              (keep whichever yields more)
                                           │
                                           ▼
                     tag: language, districts, aspects, relevance
                                           │
                                           ▼
                              SQLite (data/articles.db)
                                           │
                                           ▼
                                   CSV / JSONL export
```

### Three decisions worth knowing

**1. Google News links must be decoded, not followed.**
Modern `news.google.com/rss/articles/CBM…` links do *not* HTTP-redirect — they
return 200 on the Google URL itself. Following them gets you a Google page, not
an article. `googlenewsdecoder` resolves them via Google's batchexecute
endpoint (verified 5/5). Without this, every Google News source is dead weight.

**2. Both extractors run; the longer result wins.**
Measured on live articles:

| Article                 | trafilatura    | newspaper4k    |
| ----------------------- | -------------- | -------------- |
| amarujala/boulder-falls | 1437           | **1970** |
| amarujala/cm-dhami      | 1287           | **1879** |
| hillmail/chamoli-tunnel | **2813** | —             |

Neither dominates, and trafilatura intermittently returned 0 on a URL that
worked moments earlier. Per-site CSS parsers were rejected: six-plus outlets,
all liable to redesign.

> `newspaper4k` **requires `indic-nlp-library`** or it raises `ImportError` on
> every Devanagari page. It auto-detects language, so omitting the `language=`
> argument does not avoid this. It is pinned in `requirements.txt`.

**3. Aspect tags use a two-tier lexicon.**
`strong` terms (`पेपर लीक`, `UKSSSC`, `CBI`) assign an aspect on one hit.
Generic terms (`exam`, `student`, `investigation`) need **two** distinct
matches. This was not theoretical — a *"Child safety violations at a private
school"* story was being tagged `exam_paper_leak | protest_agitation | environment_disaster` on generic vocabulary alone. After the fix it correctly
reads `investigation_justice | health_education`.

---

## Output schema

`data/articles.db`, table `articles` (also the CSV/JSONL columns):

| Column                                        | Notes                                                                            |
| --------------------------------------------- | -------------------------------------------------------------------------------- |
| `id`                                        | SHA1 of canonical URL — stable primary key                                      |
| `url`, `canonical_url`                    | canonical strips`utm_*`, `fbclid`, `www.`/`m.`, `/amp`, trailing `/` |
| `source_name`, `publisher`, `discovery` | `discovery` is `rss` or `gnews`                                            |
| `title`, `summary`, `text`              | `summary` is the RSS lead; survives body-fetch failure                         |
| `language`                                  | `hi` / `en` / `unknown` (script-ratio heuristic)                           |
| `published_at`, `scraped_at`              | ISO8601 UTC                                                                      |
| `districts`                                 | pipe-separated, e.g.`Dehradun\|Nainital`                                        |
| `image_url`                                 | og:image lead photo (65% coverage)                                               |
| `aspects`                                   | pipe-separated, 10 categories                                                    |
| `matched_keywords`                          | which relevance terms fired — useful for auditing                               |
| `extractor`, `word_count`                 | provenance                                                                       |
| `sentiment_label`, `sentiment_score`      | **left NULL — Phase 3 writes these**                                      |

The sentiment columns already exist so the Phase 3 model can `UPDATE` in place
rather than migrating the schema.

### Aspect categories

`recruitment_jobs`, `exam_paper_leak`, `investigation_justice`,
`protest_agitation`, `infrastructure`, `environment_disaster`,
`migration_demography`, `health_education`, `tourism_religion`,
`politics_governance`

These map directly onto the Aspect-Based Sentiment objective (doc §3.2) and the
grievances in §2. Districts cover all 13 Uttarakhand districts including major
towns (Haldwani → Nainital, Rishikesh → Dehradun).

---

## Known limitations

- **News18 blocks article-page fetches** (HTTP 403 on any non-browser
  User-Agent — even its `robots.txt` 403s). Its RSS *is* served and carries
  substantial summary paragraphs, so those 200 items are stored as
  title + summary with `text` empty. That is still usable sentiment input.
  The scraper does **not** spoof a browser UA to get around this; see below.
- **Relevance gate is lexicon-based**, not semantic. An Uttarakhand story that
  names no place or institution can slip through the Google News gate. Local
  RSS sources bypass the gate by design (`trusted_source`).
- **Language detection is a script-ratio heuristic**, not a model. Romanised
  Hinglish is labelled `en` and needs the Phase 2 translation step.
- **No comment scraping.** The project doc mentions article *comments*; most of
  these outlets render comments via JS widgets (Facebook/Disqus) that need
  Selenium/Playwright. Not built — flagging as a scoping decision, not an
  oversight.

## Crawling conduct

Fixed identifying User-Agent, `robots.txt` honoured per domain, 1.5s delay
between hits on the same domain, bounded retries with backoff.

Worth knowing: **Amar Ujala's `robots.txt` blocks AI crawlers by name**
(`ClaudeBot`, `anthropic-ai`, `CCBot`, `Bytespider`, …) while allowing
`User-agent: *` on news paths. This scraper falls under `*` and is permitted —
but if you rename the bot to anything on that list, it must stop. If you ever
add a browser-UA fallback to defeat the News18 403, understand that you are
deliberately circumventing an access control the publisher put up; that is a
call for the project owner, not a default.

---

## Tests

```bash
python tests/test_pipeline.py     # or: python -m pytest tests/ -v
```

21 offline tests, no network. They cover URL canonicalisation/dedupe, store
idempotency, language detection, district tagging, the relevance gate, and the
knowledge graph — plus regression tests for five bugs found in real data:
aspect over-firing, the government-relevance gate, Devanagari tokenisation,
graph node counts disagreeing with their own drill-down, and a rate limiter
that slept while holding the global lock (which made N crawl threads run at
the speed of one).

---

## Sentiment scoring (Phase 3)

```bash
python -m uk_news.sentiment          # scores every unscored article
```

Model: **`cardiffnlp/twitter-xlm-roberta-base-sentiment`** — XLM-RoBERTa,
3-class, multilingual. Writes `sentiment_label` and a signed
`sentiment_score` = P(positive) − P(negative) in [−1, +1].

VADER and TextBlob were rejected: both are English-only lexicons, and 274 of
326 articles are Hindi. They would score every Devanagari article neutral and
silently flatten the dataset. Verified 6/6 correct on a mixed Hindi/English
probe before adoption.

**The result is the finding.** Across 326 articles: **259 neutral (79%)**, 35
negative, 32 positive. News reports factually; it does not emote. Public
comments would never produce this distribution — which is the clearest
evidence that news tone is not a proxy for public opinion.

---

## Dashboard

```bash
streamlit run app.py
```

Three modules:

Four tabs across the top of the page (no sidebar):

**1 · Scraper** — two modes.
*💾 Use local database* (the default) browses everything already collected,
fully offline: filters, full-text search, emoji sentiment summary, article
cards and a CSV download. *🌐 Scrape new articles* runs a live Google News
search by keyword or #hashtag (`when:Nd` applies the date window at source),
decodes the redirect links, fetches bodies and images, scores sentiment, and
stores — from one button.

**2 · Analysis** — emoji sentiment faces, coverage tone as a diverging stacked
bar, tone over time, aspect breakdown, TF-IDF/KMeans topics and per-publisher
tone. Every chart has a table-view twin.

**3 · Knowledge Graph** — a relation network rather than a ranking. Nodes are
**sources** (blue), **issues** (orange) and **districts** (green); an edge means
they co-occur in the same articles, thicker where they co-occur more. So you
can read off *which publisher covers which issue, in which district*.
**Click any node** to open its articles. Sliders control how many sources
appear and the minimum link strength — the main defence against a hairball.

**4 · Articles** — a three-column visual gallery: thumbnail, headline, source,
emoji sentiment pill with score, and district/aspect tags. Search and filter
by sentiment.

### Article images

`extract_image()` reads `og:image` from each page — the photo the publisher
chose for social sharing, which is far more reliable than the `<img>` tags in
the body (lazy-loading placeholders and ad slots). **215 of 332 articles (65%)
have one**; the rest are the News18 403s and pages serving no card metadata,
which fall back to a tinted initial tile. Backfill older rows with:

```bash
python -m uk_news.backfill_images
```

### Emoji sentiment

Sentiment is shown as emoji **and** colour **and** the written label
(🙂 positive / 😐 neutral / 😠 negative), never any one alone — so it survives
colour-blindness and missing emoji fonts alike.

### The one thing to be careful about

The dashboard says this in a banner on every screen, and it should stay there:

> This measures the tone of **news coverage** — how newspapers reported an
> event. That is **media sentiment**, not public opinion. No citizen was
> surveyed.

Public reaction needs comment data (YouTube Data API is free: 10,000 units/day,
`commentThreads.list` costs 1 unit). Presenting article tone as "public
approval" would be a fabricated statistic.

### Government relevance filter

`is_government_related()` deliberately ignores the word "Uttarakhand" on its
own and requires an institution (UKSSSC, विधानसभा) or an office-holder
(मुख्यमंत्री, धामी). Without it, the two most *positive* articles in the first
scored run were a horoscope and a Dehradun restaurant round-up. Of 326
articles, 122 pass this filter.

### Chart colour

Sentiment is polarity, so it uses a **diverging** scale — blue (positive) ↔
gray (neutral) ↔ red (negative) — not categorical hues. Validated against the
light surface `#fcfcfb`: CVD separation ΔE 8.7 (target ≥ 8), normal-vision
ΔE 17.8 (floor ≥ 15), contrast ≥ 3:1. The theme is pinned to light in
`.streamlit/config.toml` so charts render on the surface the palette was
validated against; re-run the validator before switching to dark.

---

## Hand-off to the next module

```python
from uk_news import Store

store = Store("data/articles.db")
for row in store.conn.execute(
        "SELECT id, title, text, summary, language, aspects, "
        "sentiment_label, sentiment_score FROM articles"):
    ...
```

Or start from `data/articles.csv` with pandas. Use `best_text` semantics —
fall back to `summary` when `text` is empty — so News18 rows are not silently
dropped.

**Next module: YouTube comments.** Same architecture carries over — the
district/aspect tagger and the SQLite store already work on Hindi text. That
is where actual public sentiment lives.
