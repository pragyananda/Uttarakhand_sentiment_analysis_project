"""Polite HTTP layer: per-domain rate limiting, robots.txt, bounded retries.

This is a government-facing research prototype, so the crawler identifies
itself honestly and throttles per domain rather than hammering regional
outlets that run on modest infrastructure.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import requests

log = logging.getLogger(__name__)


class PoliteSession:
    def __init__(
        self,
        user_agent: str,
        per_domain_delay: float = 1.5,
        timeout: int = 25,
        max_retries: int = 2,
        respect_robots: bool = True,
    ):
        self.user_agent = user_agent
        self.per_domain_delay = per_domain_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.respect_robots = respect_robots

        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml,"
                      "application/rss+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "hi-IN,hi;q=0.9,en-IN;q=0.8,en;q=0.7",
        })

        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, Optional[RobotFileParser]] = {}
        self._lock = threading.Lock()

    # -- throttling --------------------------------------------------------
    def _wait_turn(self, domain: str) -> None:
        """Rate-limit per domain, without serialising unrelated domains.

        The sleep MUST happen outside the lock. Holding the global lock while
        sleeping turns a per-domain delay into a global one: every worker
        queues behind every other, so N threads crawl at the speed of one.
        Here the slot is reserved atomically, then the wait happens unlocked.
        """
        while True:
            with self._lock:
                now = time.monotonic()
                last = self._last_hit.get(domain)
                if last is None or (now - last) >= self.per_domain_delay:
                    self._last_hit[domain] = now
                    return
                gap = self.per_domain_delay - (now - last)
            time.sleep(gap)

    # -- robots ------------------------------------------------------------
    def _allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        domain = urlsplit(url).netloc.lower()
        if domain not in self._robots:
            rp: Optional[RobotFileParser] = RobotFileParser()
            robots_url = f"{urlsplit(url).scheme}://{domain}/robots.txt"
            try:
                resp = self._session.get(robots_url, timeout=10)
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # No robots.txt served == nothing disallowed.
                    rp = None
            except requests.RequestException:
                rp = None            # unreachable robots must not block the run
            self._robots[domain] = rp

        rp = self._robots[domain]
        if rp is None:
            return True
        return rp.can_fetch(self.user_agent, url)

    # -- fetch -------------------------------------------------------------
    def get(self, url: str) -> Optional[requests.Response]:
        """Fetch a URL, or return None if blocked/failed after retries."""
        if not self._allowed(url):
            log.info("robots.txt disallows %s — skipping", url)
            return None

        domain = urlsplit(url).netloc.lower()
        for attempt in range(self.max_retries + 1):
            self._wait_turn(domain)
            try:
                resp = self._session.get(
                    url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                log.debug("attempt %d failed for %s: %s", attempt + 1, url, exc)
                if attempt == self.max_retries:
                    log.warning("giving up on %s (%s)", url, type(exc).__name__)
                    return None
                time.sleep(2 ** attempt)
                continue

            if resp.status_code == 200:
                return resp
            # 429/5xx are worth another try; 4xx are not.
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                time.sleep(2 ** attempt * 2)
                continue
            log.warning("HTTP %s for %s", resp.status_code, url)
            return None
        return None

    def get_text(self, url: str) -> Optional[str]:
        resp = self.get(url)
        if resp is None:
            return None
        # Regional Hindi sites frequently mis-declare charset; let requests
        # fall back to apparent encoding rather than mangling Devanagari.
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text
