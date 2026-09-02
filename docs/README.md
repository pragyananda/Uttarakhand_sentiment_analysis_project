# Static demo — Uttarakhand Public Sentiment dashboard

A fully static, click-only version of the Streamlit dashboard. All 332 articles
(with sentiment scores, government flags, aspect/district tags and precomputed
TF-IDF + KMeans topics) are baked into `data.js`, so the page needs **no server,
no database and no Python** — it runs anywhere plain HTML is hosted.

| File | Purpose |
|---|---|
| `index.html` | The whole dashboard — all 4 tabs, charts, knowledge graph, filters |
| `data.js` | Snapshot of `data/articles.db`, exported at build time |
| `.nojekyll` | Tells GitHub Pages to serve files as-is |

What works: all filters (date range, language, publisher, government-only),
search (Hindi + English), the sentiment charts and tables, the topics slider,
the clickable knowledge graph, the article galleries, and CSV download of the
current selection.

What doesn't (by design): live scraping and re-scoring — those need the full
Python pipeline (`streamlit run app.py`).

## Deploy on GitHub Pages

1. Commit and push this `docs/` folder to the `main` branch.
2. On GitHub: **Settings → Pages → Build and deployment**
   - Source: *Deploy from a branch*
   - Branch: `main`, folder: `/docs`
3. The site appears at `https://<username>.github.io/<repo>/` in a minute or two.

## Deploy on Vercel

1. Import the repo at [vercel.com/new](https://vercel.com/new).
2. Framework preset: **Other**. Set **Output Directory** to `docs`
   (leave build command empty).
3. Deploy — done.

Or from the terminal: `cd docs && npx vercel deploy --prod`.

## Refreshing the data

After scraping/scoring new articles with the Python app, regenerate the
snapshot (the export script lives outside the repo; it reads `data/articles.db`
and rewrites `docs/data.js`), then commit and push — the host redeploys
automatically.
