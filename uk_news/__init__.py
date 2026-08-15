"""Uttarakhand newspaper scraper — Phase 1 ingestion layer.

Public surface:

    from uk_news import run, Store, Article

    report = run(limit_per_source=10, skip_gnews=True)
    print(report.render())
"""

from .models import Article, canonicalize_url
from .pipeline import run, load_config, RunReport
from .storage import Store
from .relevance import Tagger, detect_language

__version__ = "1.0.0"

__all__ = [
    "Article", "canonicalize_url", "run", "load_config", "RunReport",
    "Store", "Tagger", "detect_language", "__version__",
]
