"""Relevance filtering, district tagging and aspect tagging.

Matching rules differ by script, deliberately:

* Devanagari terms are matched as plain substrings. Hindi inflects heavily
  (भर्ती -> भर्तीयों, भर्ती-घोटाला) and \\b word boundaries do not behave
  usefully against Devanagari in Python's `re`, so substring matching is both
  simpler and more accurate here.
* Latin-script terms are matched on word boundaries, otherwise short tokens
  like "SIT" or "job" fire inside unrelated words ("visit", "jobber").
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

# Any Devanagari codepoint means "treat as Hindi surface form".
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def has_devanagari(text: str) -> bool:
    return bool(_DEVANAGARI.search(text))


def detect_language(text: str) -> str:
    """Cheap script-ratio language guess — hi / en / unknown.

    Deliberately not a model: we only need to route text to the right
    sentiment pipeline in Phase 3, and script ratio is decisive for Hindi vs
    English. Romanised Hinglish reads as `en` here and is handled downstream
    by translation (project doc §3.2).
    """
    if not text:
        return "unknown"
    sample = text[:2000]
    deva = len(_DEVANAGARI.findall(sample))
    latin = sum(1 for c in sample if "a" <= c.lower() <= "z")
    if deva + latin < 20:
        return "unknown"
    return "hi" if deva > latin * 0.3 else "en"


def _compile(terms: Iterable[str]) -> list[tuple[str, re.Pattern | None]]:
    """Pre-compile each term to (term, pattern|None); None means substring."""
    compiled = []
    for term in terms:
        t = term.strip()
        if not t:
            continue
        if has_devanagari(t):
            compiled.append((t, None))
        else:
            compiled.append((t, re.compile(rf"\b{re.escape(t)}", re.I)))
    return compiled


def _find(text: str, compiled: list[tuple[str, re.Pattern | None]]) -> list[str]:
    hits = []
    for term, pattern in compiled:
        if pattern is None:
            if term in text:
                hits.append(term)
        elif pattern.search(text):
            hits.append(term)
    return hits


class Tagger:
    """Holds the compiled lexicons from config/keywords.yaml."""

    def __init__(self, cfg: dict):
        self.min_hits = int(cfg.get("min_relevance_hits", 1))

        self._relevance = {
            group: _compile(terms)
            for group, terms in (cfg.get("relevance") or {}).items()
        }
        self._districts = {
            name: _compile(terms)
            for name, terms in (cfg.get("districts") or {}).items()
        }

        # Aspects are two-tier. A single generic word like "student" or
        # "investigation" is not evidence of an aspect — a school-safety story
        # was being tagged exam_paper_leak + protest_agitation on exactly that
        # basis. So `strong` terms (e.g. "पेपर लीक", "UKSSSC") assign the
        # aspect on one hit, while `terms` need `min_aspect_hits` corroborating
        # matches. A bare list in YAML is treated as `terms`.
        self.min_aspect_hits = int(cfg.get("min_aspect_hits", 2))
        self._aspects: dict[str, dict[str, list]] = {}
        for name, spec in (cfg.get("aspects") or {}).items():
            if isinstance(spec, dict):
                strong, weak = spec.get("strong") or [], spec.get("terms") or []
            else:
                strong, weak = [], spec or []
            self._aspects[name] = {
                "strong": _compile(strong),
                "terms": _compile(weak),
            }

    @staticmethod
    def _normalise(text: str) -> str:
        # NFC so precomposed vs decomposed Devanagari compare equal.
        return unicodedata.normalize("NFC", text or "")

    def government_hits(self, text: str) -> list[str]:
        """Terms tying the article to the GOVERNMENT specifically.

        Deliberately narrower than `relevance_hits`: it ignores the `state`
        group, because "Uttarakhand" alone matches horoscopes and restaurant
        round-ups. Only institutions (UKSSSC, विधानसभा) and office-holders
        (मुख्यमंत्री, धामी) count.
        """
        text = self._normalise(text)
        hits: list[str] = []
        for group in ("institutions", "figures"):
            compiled = self._relevance.get(group)
            if compiled:
                hits.extend(_find(text, compiled))
        return sorted(set(hits))

    def is_government_related(self, text: str) -> bool:
        return bool(self.government_hits(text))

    def relevance_hits(self, text: str) -> list[str]:
        text = self._normalise(text)
        hits: list[str] = []
        for compiled in self._relevance.values():
            hits.extend(_find(text, compiled))
        return hits

    def districts(self, text: str) -> list[str]:
        text = self._normalise(text)
        return [name for name, compiled in self._districts.items()
                if _find(text, compiled)]

    def aspects(self, text: str) -> list[str]:
        """Multi-label aspect tags. See `min_aspect_hits` for the two tiers."""
        text = self._normalise(text)
        found = []
        for name, tiers in self._aspects.items():
            if _find(text, tiers["strong"]):
                found.append(name)
                continue
            if len(set(_find(text, tiers["terms"]))) >= self.min_aspect_hits:
                found.append(name)
        return found

    def tag(self, article, trusted_source: bool = False) -> bool:
        """Enrich an article in place; return True if it should be kept.

        `trusted_source=True` marks feeds that are already Uttarakhand-scoped
        (the local RSS sources). Those bypass the relevance gate — a Dehradun
        civic story may never say the word "Uttarakhand", but it is exactly
        the sentiment we want. The gate exists for Google News and national
        outlets, which do leak unrelated stories.
        """
        blob = f"{article.title}\n{article.summary}\n{article.text}"

        hits = self.relevance_hits(blob)
        article.matched_keywords = sorted(set(hits))
        article.districts = self.districts(blob)
        article.aspects = self.aspects(blob)
        if not article.language or article.language == "unknown":
            article.language = detect_language(blob)

        if trusted_source:
            return True
        return len(set(hits)) >= self.min_hits
