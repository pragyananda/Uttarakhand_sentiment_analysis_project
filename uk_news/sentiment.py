"""Phase 3 sentiment scoring — multilingual, Hindi + English.

Model: `cardiffnlp/twitter-xlm-roberta-base-sentiment` (XLM-RoBERTa, 3-class).
Chosen over VADER/TextBlob because 274 of our 326 articles are Hindi and both
of those are English-only lexicons — they would score Devanagari as neutral and
silently flatten the entire dataset.

IMPORTANT — what this measures
------------------------------
This scores the **tone of the news article**, i.e. how the newspaper reported
the event. That is MEDIA SENTIMENT, not PUBLIC SENTIMENT. Nobody asked a
citizen anything. Do not label this output "public opinion" on any dashboard;
the UI keeps the distinction explicit.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

log = logging.getLogger(__name__)

MODEL_NAME = "cardiffnlp/twitter-xlm-roberta-base-sentiment"

# Headline + lead carries the editorial stance; the tail of a long article
# drifts into unrelated detail and dilutes the signal.
MAX_CHARS = 1200


class SentimentScorer:
    def __init__(self, model_name: str = MODEL_NAME, batch_size: int = 16):
        self.model_name = model_name
        self.batch_size = batch_size
        self._pipe = None

    def _load(self):
        if self._pipe is None:
            from transformers import pipeline
            log.info("loading %s …", self.model_name)
            self._pipe = pipeline(
                "sentiment-analysis",
                model=self.model_name,
                truncation=True,
                max_length=512,
                top_k=None,           # return all three class scores
            )
        return self._pipe

    @staticmethod
    def _prep(title: str, body: str) -> str:
        title = (title or "").strip()
        body = (body or "").strip()
        text = f"{title}. {body}" if title else body
        return text[:MAX_CHARS]

    def score_texts(self, texts: list[str]) -> list[tuple[str, float]]:
        """Return (label, signed_score) per text.

        signed_score = P(positive) - P(negative), in [-1, +1], matching the
        polarity range the project document asks for.
        """
        if not texts:
            return []
        pipe = self._load()
        out: list[tuple[str, float]] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i: i + self.batch_size]
            for scores in pipe(chunk, batch_size=self.batch_size):
                probs = {d["label"].lower(): d["score"] for d in scores}
                signed = probs.get("positive", 0.0) - probs.get("negative", 0.0)
                label = max(probs, key=probs.get)
                out.append((label, round(signed, 4)))
        return out

    def score_one(self, title: str, body: str = "") -> tuple[str, float]:
        return self.score_texts([self._prep(title, body)])[0]


def score_database(db_path: str = "data/articles.db",
                   rescore: bool = False,
                   batch_size: int = 16,
                   progress=None) -> int:
    """Score every unscored article in the DB. Returns rows updated."""
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    where = "" if rescore else "WHERE sentiment_label IS NULL"
    rows = list(conn.execute(
        f"SELECT id, title, text, summary FROM articles {where}"))
    if not rows:
        conn.close()
        return 0

    scorer = SentimentScorer(batch_size=batch_size)
    texts = [scorer._prep(r["title"], r["text"] or r["summary"]) for r in rows]

    log.info("scoring %d articles…", len(texts))
    results: list[tuple[str, float]] = []
    step = max(batch_size, 32)
    for i in range(0, len(texts), step):
        results.extend(scorer.score_texts(texts[i: i + step]))
        if progress:
            progress(min(i + step, len(texts)), len(texts))

    conn.executemany(
        "UPDATE articles SET sentiment_label=?, sentiment_score=? WHERE id=?",
        [(lab, sc, r["id"]) for r, (lab, sc) in zip(rows, results)])
    conn.commit()
    conn.close()
    return len(results)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    def _p(done, total):
        print(f"    {done}/{total}", flush=True)

    n = score_database(progress=_p)
    print(f"scored {n} articles")
