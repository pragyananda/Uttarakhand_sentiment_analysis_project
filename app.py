"""Uttarakhand Public Sentiment — demo dashboard.

    streamlit run app.py

Four tabs across the top (not a sidebar):
  1. Scraper    — live scrape OR browse the local database already collected
  2. Analysis   — topics, article sentiment, sources
  3. Graph      — source ↔ issue ↔ district knowledge graph
  4. Articles   — visual card gallery
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from uk_news import analysis, graph as ukgraph, pipeline      # noqa: E402
from uk_news.relevance import Tagger                          # noqa: E402
from ui import theme                                          # noqa: E402

DB_PATH = ROOT / "data" / "articles.db"

st.set_page_config(page_title="Uttarakhand Public Sentiment",
                   page_icon="🏔️", layout="wide")
st.markdown(theme.CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- data ----
@st.cache_data(ttl=60)
def load_data(_token: int):
    df = analysis.load_dataframe(DB_PATH)
    if df.empty:
        return df
    _, keywords_cfg = pipeline.load_config()
    return analysis.add_government_flag(df, Tagger(keywords_cfg))


if "token" not in st.session_state:
    st.session_state["token"] = 0


def refresh():
    st.session_state["token"] += 1
    load_data.clear()


df_all = load_data(st.session_state["token"])


# -------------------------------------------------------------- header ----
st.markdown(
    '<div class="uk-hero"><h1>🏔️ Uttarakhand Public Sentiment '
    '&amp; Opinion Mining</h1></div>', unsafe_allow_html=True)

st.markdown(
    '<div class="uk-caveat">'
    '<b>⚠️ What this measures:</b> the tone of <b>news coverage</b> — how '
    'newspapers reported an event. This is <b>media sentiment</b>, not public '
    'opinion; no citizen was surveyed. Public reaction requires comment data '
    '(YouTube / social), which is a separate module. '
    'Treat every number here as “how it was reported”, never as “what people think”.'
    '</div>', unsafe_allow_html=True)

if not df_all.empty:
    # Each tile carries a small visual driven by real data — a volume
    # sparkline, a coverage meter, a tone split — rather than an icon that
    # only decorates. The number stays the point; the visual gives it shape.
    per_day = df_all.groupby("day").size().sort_index()
    govt_n = int(df_all["is_government"].sum())
    govt_pct = govt_n / len(df_all) * 100
    counts = df_all["sentiment_label"].value_counts()
    neg = int(counts.get("negative", 0))
    neu = int(counts.get("neutral", 0))
    pos = int(counts.get("positive", 0))
    imgs = int(df_all["image_url"].fillna("").ne("").sum())
    top_issue, top_issue_series, top_issue_n = "", [], 0
    _asp = analysis.explode_by(df_all, "aspects")
    if not _asp.empty:
        top_issue = _asp["tag"].value_counts().index[0]
        _top = _asp[_asp["tag"] == top_issue]
        top_issue_n = int(_top["id"].nunique())
        # This tile's sparkline must track THIS issue over time, not overall
        # volume — a chart under a label has to be about that label.
        top_issue_series = (_top.groupby("day")["id"].nunique()
                            .reindex(per_day.index, fill_value=0).tolist())

    latest_day = df_all["day"].max()
    newest_n = int((df_all["day"] == latest_day).sum())

    c = st.columns(5)
    c[0].markdown(theme.stat_tile(
        "📰 Articles collected", f"{len(df_all):,}",
        f"{per_day.mean():.0f} per day average",
        accent=theme.SERIES_1,
        viz=theme.sparkline(per_day.tolist())), unsafe_allow_html=True)

    c[1].markdown(theme.stat_tile(
        "🏛️ Government-related", f"{govt_n}",
        f"{govt_pct:.0f}% of all articles",
        accent="#4a3aa7",
        viz=theme.meter(govt_pct, color="#4a3aa7")), unsafe_allow_html=True)

    c[2].markdown(theme.stat_tile(
        "😐 Coverage tone",
        f"{neu / max(len(df_all), 1) * 100:.0f}% neutral",
        f"😠 {neg}  ·  😐 {neu}  ·  🙂 {pos}",
        accent=theme.NEUTRAL,
        viz=theme.tone_bar(neg, neu, pos)), unsafe_allow_html=True)

    img_pct = imgs / max(len(df_all), 1) * 100
    c[3].markdown(theme.stat_tile(
        "🖼️ With lead photo", f"{imgs}",
        f"{img_pct:.0f}% · {df_all['publisher'].nunique()} publishers",
        accent="#eb6834",
        viz=theme.meter(img_pct, color="#eb6834")), unsafe_allow_html=True)

    c[4].markdown(theme.stat_tile(
        "🔥 Most covered issue", top_issue or "—",
        f"{top_issue_n} articles · latest {latest_day}",
        accent="#1baf7a",
        viz=theme.sparkline(top_issue_series, color="#1baf7a")),
        unsafe_allow_html=True)
else:
    st.warning("No articles yet — open **Scraper** and run one, or "
               "`python -m uk_news scrape` from the terminal.")

st.markdown("")

TAB_SCRAPE, TAB_ANALYSIS, TAB_GRAPH, TAB_ARTICLES = st.tabs([
    "1 · Scraper",
    "2 · Analysis",
    "3 · Knowledge Graph",
    "4 · Articles",
])


# ----------------------------------------------------------- components ---
@contextmanager
def card(title: str, sub: str = ""):
    """Bordered card that actually contains its chart.

    st.markdown cannot open a div around later Streamlit elements — it closes
    immediately, boxing only the heading. st.container is the real wrapper.
    """
    with st.container(border=True):
        st.markdown(f'<div class="uk-card-h">{title}</div>'
                    f'<div class="uk-card-s">{sub}</div>',
                    unsafe_allow_html=True)
        yield


def filter_row(df: pd.DataFrame, key: str) -> pd.DataFrame:
    """One filter row above everything it scopes — never per-chart."""
    if df.empty:
        return df
    c1, c2, c3, c4 = st.columns([2.2, 1.3, 1.3, 1.6])
    dmin, dmax = df["day"].min(), df["day"].max()
    with c1:
        rng = st.date_input("📅 Date range", value=(dmin, dmax),
                            min_value=dmin, max_value=dmax, key=f"d_{key}")
    with c2:
        langs = st.multiselect("🌐 Language", ["hi", "en"],
                               default=["hi", "en"], key=f"l_{key}")
    with c3:
        pubs = sorted([p for p in df["publisher"].dropna().unique() if p])
        sel = st.multiselect("🗞️ Publisher", pubs, default=[], key=f"p_{key}")
    with c4:
        govt = st.toggle("🏛️ Government only", value=True, key=f"g_{key}",
                         help="Requires a government institution or "
                              "office-holder in the text — not just the word "
                              "“Uttarakhand”, which also matches horoscopes "
                              "and restaurant listings.")
    out = df.copy()
    if isinstance(rng, tuple) and len(rng) == 2:
        out = out[(out["day"] >= rng[0]) & (out["day"] <= rng[1])]
    if langs:
        out = out[out["language"].isin(langs)]
    if sel:
        out = out[out["publisher"].isin(sel)]
    if govt:
        out = out[out["is_government"]]
    return out


def article_cards(df: pd.DataFrame, limit: int = 12, columns: int = 2):
    """Visual gallery of article cards with thumbnails."""
    if df.empty:
        st.caption("No articles match this selection.")
        return
    rows = df.sort_values("date", ascending=False).head(limit)
    cols = st.columns(columns)
    for i, (_, r) in enumerate(rows.iterrows()):
        day = r["date"].date() if pd.notna(r["date"]) else "—"
        cols[i % columns].markdown(
            theme.article_card(
                title=r["title"], url=r["url"],
                publisher=r["publisher"] or r["source_name"], day=day,
                label=r["sentiment_label"], score=r["sentiment_score"],
                image=(r.get("image_url") or ""), language=r["language"],
                districts=r.get("districts", ""), aspects=r.get("aspects", "")),
            unsafe_allow_html=True)
    if len(df) > limit:
        st.caption(f"Showing {limit} of {len(df)} articles.")


def sentiment_faces(df: pd.DataFrame, compact: bool = False):
    """Emoji + percentage summary — the at-a-glance sentiment read.

    `compact` shrinks them for the graph's side panel, where three full-size
    faces wrap onto two rows in a one-third-width column.
    """
    total = max(len(df), 1)
    counts = df["sentiment_label"].value_counts()
    faces = "".join(
        theme.sentiment_face(lab, counts.get(lab, 0) / total * 100,
                             int(counts.get(lab, 0)))
        for lab in theme.SENTIMENT_ORDER)
    cls = "uk-faces compact" if compact else "uk-faces"
    st.markdown(f'<div class="{cls}">{faces}</div>', unsafe_allow_html=True)


# ====================================================== TAB 1: SCRAPER ====
with TAB_SCRAPE:
    mode = st.radio(
        "Data source",
        ["💾 Use local database (already scraped)", "🌐 Scrape new articles"],
        horizontal=True, key="scrape_mode",
        help="The local database works fully offline — no network needed.")

    st.markdown("")

    # ---- local DB mode ------------------------------------------------
    if mode.startswith("💾"):
        st.markdown("##### Browse what you have already collected")
        if df_all.empty:
            st.info("The local database is empty. Switch to **Scrape new "
                    "articles** to collect some.")
        else:
            df = filter_row(df_all, "local")
            q = st.text_input(
                "🔎 Search headlines and text",
                placeholder="e.g. UKSSSC, पेपर लीक, धामी, भर्ती")
            if q.strip():
                needle = q.strip().lower()
                mask = (df["title"].fillna("").str.lower().str.contains(needle)
                        | df["text"].fillna("").str.lower().str.contains(needle)
                        | df["summary"].fillna("").str.lower().str.contains(needle))
                df = df[mask]

            st.caption(f"**{len(df)}** of {len(df_all)} articles match.")
            if not df.empty:
                sentiment_faces(df)
                st.markdown("")
                article_cards(df, limit=12, columns=2)

                st.download_button(
                    "⬇️ Download this selection as CSV",
                    df.drop(columns=[c for c in ("govt_terms", "districts_list",
                                                 "aspects_list",
                                                 "matched_keywords_list",
                                                 "analysis_text")
                                     if c in df.columns]).to_csv(index=False),
                    file_name="uttarakhand_articles.csv", mime="text/csv")

    # ---- live scrape mode ---------------------------------------------
    else:
        st.markdown("##### Search Uttarakhand news and add it to the database")
        c1, c2, c3 = st.columns([2.4, 1, 1])
        with c1:
            keyword = st.text_input(
                "🔎 Keyword or #hashtag", value="UKSSSC",
                placeholder="e.g. UKSSSC, #Uttarakhand, पेपर लीक, धामी सरकार")
        with c2:
            window = st.selectbox("📅 Date window", [1, 3, 7, 14, 30], index=2,
                                  format_func=lambda d: f"last {d} days")
        with c3:
            lang = st.selectbox(
                "🌐 Language", ["hi", "en"], index=0,
                format_func=lambda x: "Hindi" if x == "hi" else "English")

        c4, c5, c6 = st.columns(3)
        with c4:
            limit = st.slider("Max articles", 5, 40, 15, step=5)
        with c5:
            govt_only = st.toggle("🏛️ Government only", value=True,
                                  key="scrape_govt")
        with c6:
            with_rss = st.toggle("📡 Also pull local RSS feeds", value=False,
                                 help="Amar Ujala, News18, Garhwal Post, "
                                      "Hill Mail, Devbhoomi Media")

        st.caption("Google News' `when:Nd` operator applies the date window at "
                   "the source, so we don't download a month to keep a week. "
                   "Each redirect link is decoded to the real publisher URL.")

        if st.button("🚀 Scrape", type="primary"):
            status = st.status(f"Scraping “{keyword}” …", expanded=True)
            try:
                report, kept = pipeline.run_query(
                    keyword=keyword, days=window, lang=lang, limit=limit,
                    db_path=str(DB_PATH), include_rss=with_rss,
                    government_only=govt_only,
                    on_progress=status.write)
                status.update(label=f"✅ Done — {report.inserted} new articles",
                              state="complete", expanded=False)

                m = st.columns(4)
                m[0].metric("Discovered", report.discovered)
                m[1].metric("New", report.inserted)
                m[2].metric("Already stored", report.already_stored)
                m[3].metric("Filtered out", report.dropped_irrelevant)

                if kept:
                    st.markdown("##### Newly scraped")
                    new_df = pd.DataFrame([{
                        "title": a.title, "url": a.url,
                        "publisher": a.publisher or a.source_name,
                        "source_name": a.source_name, "language": a.language,
                        "image_url": a.image_url,
                        "districts": "|".join(a.districts),
                        "aspects": "|".join(a.aspects),
                        "sentiment_label": getattr(a, "sentiment_label",
                                                   "unscored"),
                        "sentiment_score": getattr(a, "sentiment_score", None),
                        "date": pd.to_datetime(a.published_at, errors="coerce",
                                               utc=True, format="mixed"),
                    } for a in kept])
                    new_df["date"] = new_df["date"].dt.tz_localize(None)
                    sentiment_faces(new_df)
                    st.markdown("")
                    article_cards(new_df, limit=40, columns=2)
                else:
                    st.info("Nothing new — everything found was already stored "
                            "or filtered out by the government check.")
                refresh()
            except Exception as exc:
                status.update(label="Scrape failed", state="error")
                st.error(f"{type(exc).__name__}: {exc}")


# ===================================================== TAB 2: ANALYSIS ====
with TAB_ANALYSIS:
    if df_all.empty:
        st.info("No data yet.")
    else:
        df = filter_row(df_all, "an")
        if df.empty:
            st.warning("No articles match these filters.")
        else:
            st.markdown("")
            sentiment_faces(df)
            st.markdown("")

            left, right = st.columns(2)
            with left:
                with card("Coverage tone",
                          "Diverging scale — negative | neutral | positive"):
                    counts = df["sentiment_label"].value_counts()
                    total = int(counts.sum())
                    fig = go.Figure()
                    for lab in theme.SENTIMENT_ORDER:
                        n = int(counts.get(lab, 0))
                        if not n:
                            continue
                        pct = n / total * 100
                        fig.add_bar(
                            y=["tone"], x=[n], orientation="h",
                            name=f"{theme.SENTIMENT_EMOJI[lab]} {lab}",
                            marker=dict(color=theme.SENTIMENT_COLORS[lab],
                                        line=dict(color=theme.SURFACE, width=2)),
                            text=[f"{lab} {pct:.0f}%" if pct >= 12 else ""],
                            textposition="inside", insidetextanchor="middle",
                            textfont=dict(color="#ffffff", size=12),
                            hovertemplate=f"{lab}: %{{x}} ({pct:.1f}%)"
                                          "<extra></extra>")
                    fig.update_layout(barmode="stack", bargap=0.55)
                    theme.style_fig(fig, height=155, showlegend=True)
                    fig.update_xaxes(showgrid=False, showticklabels=False,
                                     linewidth=0)
                    fig.update_yaxes(showgrid=False, showticklabels=False,
                                     linewidth=0)
                    st.plotly_chart(fig, width="stretch",
                                    config={"displayModeBar": False})
                    with st.expander("Table view"):
                        st.dataframe(counts.rename("articles").to_frame(),
                                     width="stretch")

            with right:
                with card("Tone over time",
                          "Articles per day by sentiment class"):
                    tl = analysis.sentiment_timeline(df)
                    if tl.empty:
                        st.caption("No dated articles.")
                    else:
                        fig = go.Figure()
                        for lab in theme.SENTIMENT_ORDER:
                            fig.add_bar(
                                x=tl["day"], y=tl[lab],
                                name=f"{theme.SENTIMENT_EMOJI[lab]} {lab}",
                                marker=dict(
                                    color=theme.SENTIMENT_COLORS[lab],
                                    line=dict(color=theme.SURFACE, width=2)),
                                hovertemplate="%{x}<br>" + lab +
                                              ": %{y}<extra></extra>")
                        fig.update_layout(barmode="stack", bargap=0.35)
                        theme.style_fig(fig, height=252, showlegend=True)
                        st.plotly_chart(fig, width="stretch",
                                        config={"displayModeBar": False})
                        with st.expander("Table view"):
                            st.dataframe(tl, width="stretch", hide_index=True)

            with card("Issues covered",
                      "Aspect tags from the lexicon · one series, one colour"):
                asp = analysis.explode_by(df, "aspects")
                if asp.empty:
                    st.caption("No aspect tags in this slice.")
                else:
                    counts = (asp.groupby("tag")["id"].nunique()
                              .sort_values().reset_index(name="articles"))
                    fig = go.Figure(go.Bar(
                        x=counts["articles"], y=counts["tag"], orientation="h",
                        marker=dict(color=theme.SERIES_1),
                        text=counts["articles"], textposition="outside",
                        textfont=dict(color=theme.INK_SECONDARY, size=12),
                        hovertemplate="%{y}: %{x} articles<extra></extra>"))
                    theme.style_fig(fig, height=max(240, 30 * len(counts)))
                    fig.update_yaxes(showgrid=False)
                    st.plotly_chart(fig, width="stretch",
                                    config={"displayModeBar": False})
                    with st.expander("Table view"):
                        st.dataframe(counts.sort_values("articles",
                                                        ascending=False),
                                     width="stretch", hide_index=True)

            c1, c2 = st.columns([1.15, 1])
            with c1:
                with card("Extracted topics",
                          "TF-IDF + KMeans over article text · unsupervised, "
                          "so it finds themes the lexicon didn't anticipate"):
                    n_topics = st.slider("Number of topics", 3, 10, 6,
                                         key="ntop")
                    tdf = analysis.extract_topics(df, n_topics=n_topics)
                    if tdf.empty or "topic" not in tdf.columns:
                        st.caption("Not enough text to extract topics.")
                    else:
                        tsum = (tdf.groupby("topic")
                                .agg(articles=("id", "count"),
                                     mean_tone=("sentiment_score", "mean"))
                                .reset_index()
                                .sort_values("articles", ascending=False))
                        tsum["mean_tone"] = tsum["mean_tone"].round(3)
                        st.dataframe(
                            tsum, width="stretch", hide_index=True,
                            column_config={
                                "topic": st.column_config.TextColumn(
                                    "Top terms", width="large"),
                                "articles": st.column_config.NumberColumn(
                                    "Articles"),
                                "mean_tone": st.column_config.NumberColumn(
                                    "Mean tone", format="%.2f")})

            with c2:
                with card("Sources", "Who is covering this, and in what tone"):
                    src = analysis.source_breakdown(df)
                    if src.empty:
                        st.caption("No publisher data.")
                    else:
                        st.dataframe(
                            src, width="stretch", hide_index=True,
                            column_config={
                                "publisher": st.column_config.TextColumn(
                                    "Publisher"),
                                "articles": st.column_config.NumberColumn(
                                    "Articles"),
                                "mean_sentiment": st.column_config.NumberColumn(
                                    "Mean tone", format="%.2f"),
                                "negative": st.column_config.NumberColumn("Neg"),
                                "with_body": st.column_config.NumberColumn(
                                    "Full text")})


# ======================================================== TAB 3: GRAPH ====
with TAB_GRAPH:
    if df_all.empty:
        st.info("No data yet.")
    else:
        df = filter_row(df_all, "gr")
        if df.empty:
            st.warning("No articles match these filters.")
        else:
            c1, c2, c3 = st.columns(3)
            with c1:
                show_districts = st.toggle("📍 Include districts", value=True)
            with c2:
                top_sources = st.slider("Max sources", 4, 20, 10)
            with c3:
                min_w = st.slider("Minimum link strength", 1, 8, 2,
                                  help="Hide links backed by fewer than this "
                                       "many shared articles — the main "
                                       "control for hairball density.")

            nodes, edges, used = ukgraph.build_graph(
                df, include_districts=show_districts,
                top_sources=top_sources, min_edge_weight=min_w)

            if nodes.empty:
                st.warning("No connections at this threshold — lower the "
                           "minimum link strength.")
            else:
                legend = " ".join(
                    f'<span class="uk-tag" style="border-color:{v["color"]};'
                    f'color:{v["color"]};">● {v["label"]}</span>'
                    for v in ukgraph.NODE_TYPES.values())

                # Graph left, node details right — so the detail panel sits
                # beside what you clicked rather than pushing it off-screen.
                g_col, d_col = st.columns([2.45, 1], gap="medium")

                with g_col, card(
                    "Source ↔ Issue ↔ District network",
                    "Each node is a source, an issue or a district. A line "
                    "means they appear together in the same articles — thicker "
                    "means more. <b>Click any node</b> for details. "
                    + legend):

                    fig = go.Figure()

                    # Edges first so nodes sit on top of them.
                    wmax = max(int(edges["weight"].max()), 1)
                    for _, e in edges.iterrows():
                        fig.add_trace(go.Scatter(
                            x=[e["x0"], e["x1"]], y=[e["y0"], e["y1"]],
                            mode="lines", hoverinfo="skip",
                            showlegend=False,
                            line=dict(
                                width=0.6 + 3.4 * (e["weight"] / wmax),
                                color=f"rgba(11,11,11,"
                                      f"{0.07 + 0.22 * (e['weight'] / wmax):.2f})")))

                    # One trace per node type so the legend carries identity
                    # and colour is never the only channel.
                    amax = max(int(nodes["articles"].max()), 1)
                    for ntype, meta in ukgraph.NODE_TYPES.items():
                        sub = nodes[nodes["ntype"] == ntype]
                        if sub.empty:
                            continue
                        fig.add_trace(go.Scatter(
                            x=sub["x"], y=sub["y"], mode="markers+text",
                            name=meta["label"],
                            text=sub["name"], textposition="bottom center",
                            textfont=dict(size=10.5,
                                          color=theme.INK_SECONDARY),
                            marker=dict(
                                size=sub["articles"], sizemode="area",
                                sizeref=amax / (34. ** 2) * 2, sizemin=11,
                                color=meta["color"],
                                line=dict(color=theme.SURFACE, width=2)),
                            customdata=sub[["node", "articles", "degree",
                                            "tone", "connections"]].values,
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                f"type: {meta['label']}<br>"
                                "articles: %{customdata[1]}<br>"
                                "links: %{customdata[2]}<br>"
                                "mean tone: %{customdata[3]:+.2f}<br>"
                                "connected to: %{customdata[4]}"
                                "<extra></extra>")))

                    theme.style_fig(fig, height=620, showlegend=True)
                    fig.update_xaxes(showgrid=False, showticklabels=False,
                                     zeroline=False, linewidth=0)
                    fig.update_yaxes(showgrid=False, showticklabels=False,
                                     zeroline=False, linewidth=0)
                    fig.update_layout(hovermode="closest")

                    ev = st.plotly_chart(
                        fig, width="stretch", on_select="rerun",
                        selection_mode="points", key="kgraph",
                        config={"displayModeBar": False})

                # -- click-through, rendered in the right-hand column ----
                picked = None
                pts = (ev.get("selection", {}) or {}).get("points", []) if ev else []
                if pts:
                    cd = pts[0].get("customdata")
                    if cd:
                        picked = cd[0]

                with d_col:
                    row = nodes[nodes["node"] == picked] if picked else None
                    if row is None or row.empty:
                        with card("Node details",
                                  "Nothing selected yet."):
                            st.info("👆 Click any node in the graph to see its "
                                    "details, connections and articles here.")
                            st.caption(
                                f"{len(nodes)} nodes · {len(edges)} links in "
                                "the current view.")
                    else:
                        row = row.iloc[0]
                        meta = ukgraph.NODE_TYPES[row["ntype"]]
                        with card(
                                f'<span style="color:{meta["color"]};">●</span> '
                                f'{row["name"]}',
                                f'{meta["label"]} · {int(row["degree"])} '
                                f'connections'):
                            k = st.columns(2)
                            k[0].metric("Articles", int(row["articles"]))
                            k[1].metric("Mean tone", f"{row['tone']:+.2f}")

                            sub = ukgraph.articles_for_node(used, picked)
                            st.markdown("**Tone of its coverage**")
                            sentiment_faces(sub, compact=True)

                            st.markdown("**Connected to**")
                            conn = [c for c in
                                    (row["connections"] or "").split(", ") if c]
                            st.markdown(
                                "".join(f'<span class="uk-tag">{c}</span> '
                                        for c in conn) or "—",
                                unsafe_allow_html=True)

                            st.markdown("**Articles**")
                            article_cards(sub, limit=6, columns=1)

                with st.expander("Table view — nodes and their connections"):
                    st.dataframe(
                        nodes[["name", "ntype", "articles", "degree", "tone",
                               "connections"]].sort_values("degree",
                                                           ascending=False),
                        width="stretch", hide_index=True,
                        column_config={
                            "name": st.column_config.TextColumn("Node"),
                            "ntype": st.column_config.TextColumn("Type"),
                            "degree": st.column_config.NumberColumn("Links"),
                            "tone": st.column_config.NumberColumn(
                                "Mean tone", format="%.2f"),
                            "connections": st.column_config.TextColumn(
                                "Connected to", width="large")})


# ===================================================== TAB 4: ARTICLES ====
with TAB_ARTICLES:
    if df_all.empty:
        st.info("No data yet.")
    else:
        df = filter_row(df_all, "art")
        c1, c2 = st.columns([2, 1])
        with c1:
            q = st.text_input("🔎 Search", key="art_q",
                              placeholder="UKSSSC, पेपर लीक, धामी …")
        with c2:
            sent = st.multiselect(
                "Sentiment",
                [f"{theme.SENTIMENT_EMOJI[s]} {s}"
                 for s in theme.SENTIMENT_ORDER],
                default=[])
        if q.strip():
            needle = q.strip().lower()
            df = df[df["title"].fillna("").str.lower().str.contains(needle)
                    | df["text"].fillna("").str.lower().str.contains(needle)]
        if sent:
            wanted = {s.split(" ", 1)[1] for s in sent}
            df = df[df["sentiment_label"].isin(wanted)]

        st.caption(f"**{len(df)}** articles")
        if not df.empty:
            sentiment_faces(df)
            st.markdown("")
            n = st.slider("Show", 6, 48, 16, step=2, key="art_n")
            article_cards(df, limit=n, columns=3)
