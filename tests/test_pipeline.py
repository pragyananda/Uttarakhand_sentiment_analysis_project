"""Offline unit tests — no network required.

    python -m pytest tests/ -v      (or: python tests/test_pipeline.py)
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from uk_news.models import Article, canonicalize_url
from uk_news.relevance import Tagger, detect_language
from uk_news.storage import Store
from uk_news.discovery import dedupe

CFG = yaml.safe_load(
    open(Path(__file__).parent.parent / "config" / "keywords.yaml",
         encoding="utf-8"))


# --- URL canonicalisation: the basis of all deduplication ----------------
def test_canonicalize_strips_tracking_and_host_noise():
    base = "https://www.amarujala.com/dehradun/story-123"
    variants = [
        base,
        base + "?utm_source=twitter&utm_campaign=x",
        base + "/",
        "https://amarujala.com/dehradun/story-123",
        "https://m.amarujala.com/dehradun/story-123",
        base + "/amp",
        "HTTPS://WWW.AmarUjala.com/dehradun/story-123?fbclid=abc",
    ]
    canon = {canonicalize_url(v) for v in variants}
    assert len(canon) == 1, f"expected 1 canonical form, got {canon}"


def test_meaningful_query_params_survive():
    a = canonicalize_url("https://x.com/news?id=42")
    assert "id=42" in a


def test_same_story_dedupes_to_one_article():
    arts = [
        Article(url="https://www.amarujala.com/a/b?utm_source=fb",
                title="short", discovery="gnews"),
        Article(url="https://amarujala.com/a/b",
                title="short", text="x" * 500, discovery="rss"),
    ]
    out = dedupe(arts)
    assert len(out) == 1
    # richer record wins
    assert len(out[0].text) == 500
    assert out[0].discovery == "rss"


# --- language detection ---------------------------------------------------
def test_language_detection():
    assert detect_language("उत्तराखंड में भर्ती परीक्षा को लेकर प्रदर्शन हुआ") == "hi"
    assert detect_language(
        "The Uttarakhand government announced a new recruitment policy today "
        "in Dehradun after weeks of student protests.") == "en"
    assert detect_language("") == "unknown"


# --- aspect tagging -------------------------------------------------------
def test_strong_term_fires_on_single_hit():
    t = Tagger(CFG)
    assert "exam_paper_leak" in t.aspects("UKSSSC पेपर लीक मामले में सुनवाई")


def test_generic_term_alone_does_not_fire():
    """Regression: a lone 'student'/'exam' must not imply a paper leak.

    A school-safety story was previously tagged exam_paper_leak +
    protest_agitation purely on generic vocabulary.
    """
    t = Tagger(CFG)
    aspects = t.aspects("The school held its annual exam for students today.")
    assert "exam_paper_leak" not in aspects
    assert "protest_agitation" not in aspects


def test_two_generic_terms_do_fire():
    t = Tagger(CFG)
    aspects = t.aspects("परीक्षा में धांधली की शिकायत मिली है")
    assert "exam_paper_leak" in aspects


def test_multilabel():
    t = Tagger(CFG)
    aspects = t.aspects(
        "देहरादून में बेरोजगारी को लेकर युवाओं का प्रदर्शन, CBI जांच की मांग")
    for expected in ("recruitment_jobs", "protest_agitation",
                     "investigation_justice"):
        assert expected in aspects, f"missing {expected} in {aspects}"


# --- district tagging -----------------------------------------------------
def test_district_detection_hindi_and_roman():
    t = Tagger(CFG)
    assert "Pithoragarh" in t.districts("पिथौरागढ़ के मुनस्यारी में बादल फटा")
    assert "Nainital" in t.districts("A road in Haldwani was closed today.")
    assert "Dehradun" in t.districts("मसूरी में पर्यटकों की भीड़")


# --- relevance gate -------------------------------------------------------
def test_offtopic_national_story_is_rejected():
    t = Tagger(CFG)
    art = Article(url="https://toi.com/x",
                  title="Fake Amul milk racket busted in Mumbai",
                  summary="74 litres of adulterated milk seized.")
    assert t.tag(art, trusted_source=False) is False


def test_uttarakhand_story_is_kept():
    t = Tagger(CFG)
    art = Article(url="https://toi.com/y",
                  title="Uttarakhand government clears new domicile policy",
                  summary="The Dhami cabinet approved the proposal.")
    assert t.tag(art, trusted_source=True) is True
    assert t.tag(art, trusted_source=False) is True


def test_trusted_local_source_bypasses_gate():
    """A Dehradun civic story may never say the word 'Uttarakhand'."""
    t = Tagger(CFG)
    art = Article(url="https://garhwalpost.in/z",
                  title="Potholes on Rajpur Road anger residents",
                  summary="Locals complain about road conditions.")
    assert t.tag(art, trusted_source=False) is False
    assert t.tag(art, trusted_source=True) is True


# --- storage --------------------------------------------------------------
def test_store_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "t.db")
        arts = [Article(url="https://a.com/1", title="one"),
                Article(url="https://a.com/2", title="two")]
        ins, skip = store.save_many(arts)
        assert (ins, skip) == (2, 0)

        # re-running the scraper must not duplicate anything
        ins2, skip2 = store.save_many(arts)
        assert (ins2, skip2) == (0, 2)
        assert store.count() == 2

        # ...even when the URL arrives decorated differently
        ins3, _ = store.save_many(
            [Article(url="https://www.a.com/1/?utm_source=x", title="one")])
        assert ins3 == 0
        assert store.count() == 2
        store.close()


def test_best_text_falls_back_to_summary():
    a = Article(url="https://a.com/x", title="T", summary="S")
    assert a.best_text == "S"
    b = Article(url="https://a.com/y", title="T")
    assert b.best_text == "T"


def test_export_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "t.db")
        store.save_many([Article(url="https://a.com/1", title="एक",
                                 text="body", districts=["Dehradun"],
                                 aspects=["recruitment_jobs"])])
        n = store.export_csv(Path(tmp) / "o.csv")
        assert n == 1
        n = store.export_jsonl(Path(tmp) / "o.jsonl")
        assert n == 1
        import json
        rec = json.loads((Path(tmp) / "o.jsonl").read_text(encoding="utf-8"))
        assert rec["districts"] == ["Dehradun"]
        assert rec["title"] == "एक"
        store.close()


# --- government relevance gate (dashboard filter) -------------------------
def test_government_filter_rejects_non_govt_uttarakhand_story():
    """Regression: "Uttarakhand" alone is not government relevance.

    A horoscope and a Dehradun food round-up were the two most POSITIVE
    articles in the first scored run, purely because they said "Uttarakhand".
    """
    t = Tagger(CFG)
    assert t.is_government_related(
        "Kark Rashifal: कर्क राशि वालों के लिए आज का दिन उत्तराखंड में") is False
    assert t.is_government_related(
        "देहरादून के इन 5 स्पॉट्स पर मिलता है बेहतरीन खाना") is False


def test_government_filter_accepts_real_govt_story():
    t = Tagger(CFG)
    assert t.is_government_related(
        "UKSSSC भर्ती परीक्षा पर आयोग का बड़ा फैसला") is True
    assert t.is_government_related(
        "मुख्यमंत्री धामी ने की घोषणा") is True
    assert t.is_government_related(
        "Uttarakhand government cleared the new policy") is True


# --- Devanagari tokenisation for topic extraction -------------------------
def test_devanagari_tokens_keep_their_vowel_marks():
    """Regression: Python's \\w drops Devanagari matras (category Mn).

    With \\w the tokeniser shredded सरकार -> सरक and नियुक्ति -> नपत, which
    also silently disabled the Hindi stopword list.
    """
    import re
    from uk_news.analysis import TOKEN_PATTERN
    toks = re.findall(TOKEN_PATTERN,
                      "उत्तराखंड सरकार ने नियुक्ति प्रक्रिया शुरू की। UKSSSC leak")
    assert "सरकार" in toks
    assert "नियुक्ति" in toks
    assert "उत्तराखंड" in toks
    assert "UKSSSC" in toks
    # danda must not glue onto the preceding word
    assert not any(t.endswith("।") for t in toks)


# --- knowledge graph ------------------------------------------------------
def _graph_frame():
    import pandas as pd
    rows = []
    for i in range(12):
        rows.append({
            "id": f"a{i}", "url": f"https://x.com/{i}", "title": f"t{i}",
            "publisher": ["Amar Ujala", "Jagran", "Hill Mail"][i % 3],
            "source_name": "s", "sentiment_score": 0.1,
            "sentiment_label": "neutral",
            "aspects_list": [["recruitment_jobs"], ["exam_paper_leak"]][i % 2],
            "districts_list": [["Dehradun"], ["Nainital"]][i % 2],
        })
    return pd.DataFrame(rows)


def test_graph_builds_typed_nodes_and_edges():
    from uk_news.graph import build_graph, NODE_TYPES
    nodes, edges, used = build_graph(_graph_frame(), min_edge_weight=1)
    assert not nodes.empty and not edges.empty
    assert set(nodes["ntype"]).issubset(set(NODE_TYPES))
    # every edge must join two real nodes
    known = set(nodes["node"])
    assert set(edges["source"]).issubset(known)
    assert set(edges["target"]).issubset(known)


def test_graph_node_count_matches_its_drilldown():
    """Regression: a node claiming 32 articles opened a list of 37.

    Node counts are computed on the top-publishers subset, so the click-through
    must filter the SAME frame (`used`), not the caller's full frame.
    """
    from uk_news.graph import build_graph, articles_for_node
    nodes, _, used = build_graph(_graph_frame(), top_sources=2,
                                 min_edge_weight=1)
    for _, row in nodes.iterrows():
        got = len(articles_for_node(used, row["node"]))
        assert got == row["articles"], (
            f"{row['node']}: node says {row['articles']}, drilldown {got}")


# --- rate limiter ---------------------------------------------------------
def test_rate_limiter_does_not_serialise_across_domains():
    """Regression: _wait_turn slept while holding the GLOBAL lock, so a slow
    domain blocked every other worker even when their domains were idle.

    The naive "time 4 domains in parallel" check passes either way — by the
    time a blocked thread wins the lock its own delay has already elapsed.
    This measures what actually differs: how long a FRESH domain is made to
    wait while one busy domain is serving out its delay.
    Buggy: 0.50s. Fixed: ~0.00s.
    """
    import time
    from concurrent.futures import ThreadPoolExecutor
    from uk_news.net import PoliteSession

    s = PoliteSession(user_agent="t", per_domain_delay=0.5)
    s._wait_turn("busy")          # only this domain owes a wait

    latency = {}

    def call(domain):
        start = time.monotonic()
        s._wait_turn(domain)
        latency[domain] = time.monotonic() - start

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(call, ["busy", "fresh1", "fresh2", "fresh3"]))

    worst_fresh = max(latency[d] for d in ("fresh1", "fresh2", "fresh3"))
    assert worst_fresh < 0.2, (
        f"idle domains blocked {worst_fresh:.2f}s behind a busy one")


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items())
           if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {name}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {name}: {type(e).__name__}: {e}")
    print(f"\n  {len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
