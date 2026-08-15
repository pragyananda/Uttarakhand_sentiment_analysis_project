"""Analysis layer: topic extraction and dashboard aggregations.

Everything here reads the SQLite store and returns pandas frames the UI can
render directly. No plotting happens in this module — keeping the aggregation
testable and separate from the presentation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd

# Hindi + English stopwords. sklearn ships English only, and without the Hindi
# list every "topic" comes back as है / को / में / से.
HINDI_STOPWORDS = """
का की के को में से पर है हैं था थे थी और भी नहीं यह वह ये वे कि जो तो ही हो
कर करने किया गया गई गए एक दो लिए बाद साथ तक अब जब तब कुछ सभी सब अपने अपनी
इस उस इन उन हुआ हुई हुए रहा रही रहे होगा होगी होंगे कहा बताया गयी लेकिन या
मैं हम आप उनके इसके अपना यहां वहां जहां कैसे क्यों क्या कोई सकता सकते सकती
द्वारा दौरान बारे तरह ओर आदि प्रति हेतु व एवं जा ने पास फिर बहुत ज्यादा
""".split()

ENGLISH_EXTRA = """
said says new news report reports according told also would could will
year years day days time first last one two three said_the mr uttarakhand
state government
""".split()

# Boilerplate that leaks in from embedded JSON-LD / page metadata when an
# extractor grabs more than the article body.
JUNK_TOKENS = """
slug title_hn title_en states city url href http https www com html img src
div span class data json var function null true false none nbsp amp
""".split()

# Devanagari tokens must be matched by codepoint range, NOT by \\w.
# Python's \\w follows str.isalnum(), which excludes non-spacing marks (Mn) —
# and every Hindi vowel sign (ा ि ी ु ू े ो ्) is Mn. Using \\w therefore
# strips the matras and shreds each word: सरकार -> सरक, नियुक्ति -> नपत.
# That also silently broke the stopword list above, since none of its
# properly-spelled entries could ever match a mangled token.
# The range below covers Devanagari but excludes the danda U+0964/U+0965,
# which is sentence punctuation and would otherwise glue onto words.
TOKEN_PATTERN = r"(?u)[A-Za-z]{3,}|[ऀ-ॣ०-ॿ]{3,}"


def load_dataframe(db_path: str | Path = "data/articles.db") -> pd.DataFrame:
    """Read all articles into a frame with parsed dates and list columns."""
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql_query("SELECT * FROM articles", conn)
    conn.close()
    if df.empty:
        return df

    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce",
                                        utc=True, format="mixed")
    df["scraped_at"] = pd.to_datetime(df["scraped_at"], errors="coerce",
                                      utc=True, format="mixed")
    # Fall back to scrape time so undated articles still land on the timeline.
    df["date"] = df["published_at"].fillna(df["scraped_at"]).dt.tz_localize(None)
    df["day"] = df["date"].dt.date

    for col in ("districts", "aspects", "matched_keywords"):
        df[col + "_list"] = df[col].fillna("").apply(
            lambda s: [x for x in s.split("|") if x])

    df["sentiment_score"] = pd.to_numeric(df["sentiment_score"],
                                          errors="coerce")
    df["sentiment_label"] = df["sentiment_label"].fillna("unscored")
    df["analysis_text"] = (df["title"].fillna("") + ". "
                           + df["text"].fillna("").str.slice(0, 1500))
    return df


def add_government_flag(df: pd.DataFrame, tagger) -> pd.DataFrame:
    """Flag articles that actually concern the state government.

    Needed because matching "Uttarakhand" alone lets horoscopes and food
    round-ups into a government sentiment dashboard — both showed up in the
    top-positive articles of the first scored run.
    """
    if df.empty:
        return df
    df = df.copy()
    blob = (df["title"].fillna("") + " " + df["summary"].fillna("") + " "
            + df["text"].fillna("").str.slice(0, 2000))
    df["govt_terms"] = blob.apply(tagger.government_hits)
    df["is_government"] = df["govt_terms"].apply(bool)
    return df


def explode_by(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """One row per (article, tag) for a pipe-separated list column."""
    col = column if column.endswith("_list") else column + "_list"
    if col not in df.columns:
        return pd.DataFrame()
    out = df.explode(col).rename(columns={col: "tag"})
    return out[out["tag"].notna() & (out["tag"] != "")]


def extract_topics(df: pd.DataFrame, n_topics: int = 8,
                   terms_per_topic: int = 4) -> pd.DataFrame:
    """Cluster articles into topics with TF-IDF + KMeans.

    Labels are the top TF-IDF terms of each cluster centroid. This is
    deliberately unsupervised — it surfaces what the coverage is actually
    about, rather than only what our hand-written aspect lexicon anticipated.
    """
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import (ENGLISH_STOP_WORDS,
                                                 TfidfVectorizer)

    # Passing a custom `stop_words` list REPLACES sklearn's built-in English
    # list rather than extending it, so it has to be merged back in — without
    # this, "the · and · for · was" forms its own cluster.
    stopwords = list(ENGLISH_STOP_WORDS.union(
        HINDI_STOPWORDS + ENGLISH_EXTRA + JUNK_TOKENS))

    texts = df["analysis_text"].fillna("").tolist()
    usable = [t for t in texts if len(t.strip()) > 40]
    if len(usable) < n_topics or n_topics < 2:
        return pd.DataFrame(columns=["topic_id", "label", "count"])

    vec = TfidfVectorizer(
        max_features=4000,
        stop_words=stopwords,
        token_pattern=TOKEN_PATTERN,
        max_df=0.55,      # a term in >55% of articles isn't a topic
        min_df=2,
    )
    try:
        X = vec.fit_transform(texts)
    except ValueError:
        return pd.DataFrame(columns=["topic_id", "label", "count"])

    n_topics = min(n_topics, X.shape[0] - 1, 12)
    km = KMeans(n_clusters=n_topics, random_state=42, n_init=10)
    labels = km.fit_predict(X)

    vocab = vec.get_feature_names_out()
    names = []
    for i in range(n_topics):
        top = km.cluster_centers_[i].argsort()[::-1][:terms_per_topic]
        names.append(" · ".join(vocab[j] for j in top))

    df = df.copy()
    df["topic_id"] = labels
    df["topic"] = [names[i] for i in labels]
    return df


def bubble_data(df: pd.DataFrame, group_by: str = "aspects",
                min_articles: int = 2) -> pd.DataFrame:
    """Aggregate into bubble-chart rows.

    Returns one row per group with volume (salience), mean sentiment (tone),
    and source breadth — the three things that decide whether an issue needs
    attention.
    """
    if df.empty:
        return pd.DataFrame()

    if group_by in ("aspects", "districts"):
        work = explode_by(df, group_by)
    else:                                   # a plain column, e.g. topic
        work = df.rename(columns={group_by: "tag"})
        work = work[work["tag"].notna()]
    if work.empty:
        return pd.DataFrame()

    grouped = work.groupby("tag").agg(
        articles=("id", "nunique"),
        mean_sentiment=("sentiment_score", "mean"),
        sources=("source_name", "nunique"),
        publishers=("publisher", "nunique"),
        negative=("sentiment_label", lambda s: (s == "negative").sum()),
        positive=("sentiment_label", lambda s: (s == "positive").sum()),
        neutral=("sentiment_label", lambda s: (s == "neutral").sum()),
        latest=("date", "max"),
    ).reset_index()

    grouped = grouped[grouped["articles"] >= min_articles]
    grouped["mean_sentiment"] = grouped["mean_sentiment"].fillna(0).round(3)
    grouped["negative_share"] = (
        grouped["negative"] / grouped["articles"] * 100).round(1)
    return grouped.sort_values("articles", ascending=False)


def sentiment_timeline(df: pd.DataFrame) -> pd.DataFrame:
    """Per-day counts of each sentiment class."""
    if df.empty or "day" not in df.columns:
        return pd.DataFrame()
    out = (df.groupby(["day", "sentiment_label"]).size()
             .unstack(fill_value=0).reset_index())
    for col in ("negative", "neutral", "positive"):
        if col not in out.columns:
            out[col] = 0
    out["total"] = out[["negative", "neutral", "positive"]].sum(axis=1)
    return out.sort_values("day")


def source_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Per-publisher volume and tone — who is covering, and how."""
    if df.empty:
        return pd.DataFrame()
    out = df.groupby("publisher").agg(
        articles=("id", "count"),
        mean_sentiment=("sentiment_score", "mean"),
        negative=("sentiment_label", lambda s: (s == "negative").sum()),
        with_body=("text", lambda s: (s.fillna("") != "").sum()),
    ).reset_index()
    out = out[out["publisher"].fillna("") != ""]
    out["mean_sentiment"] = out["mean_sentiment"].fillna(0).round(3)
    return out.sort_values("articles", ascending=False)


def top_keywords(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Most frequent relevance keywords — feeds the word-cloud objective."""
    ex = explode_by(df, "matched_keywords")
    if ex.empty:
        return pd.DataFrame(columns=["keyword", "count"])
    out = (ex.groupby("tag").size().reset_index(name="count")
             .rename(columns={"tag": "keyword"}))
    return out.sort_values("count", ascending=False).head(n)
