"""
Article fetching and parsing utilities.
"""

import logging
import pickle
import re
import sqlite3
import threading
import time
import hashlib
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

from ..models.article import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent SQLite article cache
# ---------------------------------------------------------------------------

_ARTICLE_CACHE_DB = str(Path.home() / ".article_cache.db")
_ARTICLE_CACHE_TTL = 24 * 3600  # 24 hours — articles rarely change intra-day


class _PersistentArticleCache:
    """SQLite-backed article cache with TTL eviction (thread-safe).

    Articles are serialised with pickle.  Cache misses (expired or absent)
    return ``None``; callers should then fetch the live URL and call
    ``put()`` to populate the cache.
    """

    def __init__(self, db_path: str = _ARTICLE_CACHE_DB, ttl: int = _ARTICLE_CACHE_TTL) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS article_cache (
                url_hash  TEXT PRIMARY KEY,
                url       TEXT NOT NULL,
                data      BLOB NOT NULL,
                fetched_at REAL NOT NULL
            )
        """)
        self._conn.commit()
        logger.debug(f"[ArticleCache] SQLite cache opened: {db_path}")

    def get(self, url: str) -> Optional["Article"]:
        key = hashlib.md5(url.encode()).hexdigest()
        with self._lock:
            row = self._conn.execute(
                "SELECT data, fetched_at FROM article_cache WHERE url_hash=?", (key,)
            ).fetchone()
        if row is None:
            return None
        data, fetched_at = row
        if time.time() - fetched_at > self._ttl:
            logger.debug(f"[ArticleCache] Expired: {url[:80]}")
            return None
        try:
            article = pickle.loads(data)
            logger.debug(f"[ArticleCache] Hit: {url[:80]}")
            return article
        except Exception as exc:
            logger.debug(f"[ArticleCache] Deserialise error ({exc}) for {url[:80]}")
            return None

    def put(self, url: str, article: "Article") -> None:
        key = hashlib.md5(url.encode()).hexdigest()
        try:
            data = pickle.dumps(article)
        except Exception as exc:
            logger.debug(f"[ArticleCache] Serialise error ({exc}) — not cached: {url[:80]}")
            return
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO article_cache (url_hash, url, data, fetched_at) "
                "VALUES (?, ?, ?, ?)",
                (key, url, data, time.time()),
            )
            self._conn.commit()
        logger.debug(f"[ArticleCache] Stored: {url[:80]}")


# Module-level singleton — shared across all ArticleFetcher instances and threads
_persistent_cache = _PersistentArticleCache()


class ArticleFetcher:
    """Fetches and parses Microsoft support articles."""

    # Cache for fetched articles
    _cache: dict = {}
    _cache_timestamps: dict = {}

    def __init__(self, cache_ttl: int = 3600, request_delay: float = 0.5):
        """
        Initialize the article fetcher.

        Args:
            cache_ttl: Cache time-to-live in seconds
            request_delay: Delay between requests in seconds
        """
        self.cache_ttl = cache_ttl
        self.request_delay = request_delay
        self._last_request_time = 0
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key for URL."""
        return hashlib.md5(url.encode()).hexdigest()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached entry is still valid."""
        if cache_key not in self._cache_timestamps:
            return False
        timestamp = self._cache_timestamps[cache_key]
        return datetime.now() - timestamp < timedelta(seconds=self.cache_ttl)

    def _rate_limit(self):
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self._last_request_time = time.time()

    def fetch(self, url: str, use_cache: bool = True) -> Article:
        """
        Fetch and parse an article from URL.

        Lookup order:
        1. In-memory L1 cache (per-instance, fast)
        2. Persistent SQLite L2 cache (shared across runs/threads, 24 h TTL)
        3. Live HTTP request

        Args:
            url: The article URL
            use_cache: Whether to use cached results

        Returns:
            Article object with parsed content
        """
        if not url:
            return Article(url="", fetch_error="No URL provided")

        # L1: in-memory cache
        cache_key = self._get_cache_key(url)
        if use_cache and cache_key in self._cache and self._is_cache_valid(cache_key):
            return self._cache[cache_key]

        # L2: persistent SQLite cache
        if use_cache:
            cached = _persistent_cache.get(url)
            if cached is not None:
                # Backfill L1 so subsequent in-process requests are instant
                self._cache[cache_key] = cached
                self._cache_timestamps[cache_key] = datetime.now()
                return cached

        # Apply rate limiting before live fetch
        self._rate_limit()

        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()

            article = self._parse_article(url, response.text)

            # Populate both cache tiers
            self._cache[cache_key] = article
            self._cache_timestamps[cache_key] = datetime.now()
            if use_cache:
                _persistent_cache.put(url, article)

            return article

        except requests.RequestException as e:
            return Article(url=url, fetch_error=str(e))

    def _parse_article(self, url: str, html: str) -> Article:
        """
        Parse article content from HTML.

        Args:
            url: The article URL
            html: Raw HTML content

        Returns:
            Parsed Article object
        """
        soup = BeautifulSoup(html, 'html.parser')

        # Extract title
        title = self._extract_title(soup)

        # Extract main content
        content = self._extract_content(soup, url)

        # Extract metadata
        last_updated = self._extract_date(soup)
        applies_to = self._extract_applies_to(soup)
        prerequisites = self._extract_prerequisites(soup)
        steps = self._extract_steps(soup)
        article_type = self._determine_article_type(soup, content)

        return Article(
            url=url,
            title=title,
            content=content,
            last_updated=last_updated,
            applies_to=applies_to,
            prerequisites=prerequisites,
            steps=steps,
            article_type=article_type
        )

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract article title."""
        # Try different title selectors
        selectors = [
            'h1',
            'meta[property="og:title"]',
            'title'
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    return element.get('content', '')
                return element.get_text(strip=True)

        return ""

    def _extract_content(self, soup: BeautifulSoup, url: str) -> str:
        """Extract main article content."""
        # Different content selectors for different Microsoft domains
        if "learn.microsoft.com" in url:
            selectors = ['main', '.content', '#main-content', 'article']
        else:  # support.microsoft.com
            selectors = ['#supArticleContent', '.ocpArticleContent', 'main', 'article']

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                # Remove script and style elements
                for script in element(['script', 'style', 'nav', 'header', 'footer']):
                    script.decompose()

                text = element.get_text(separator='\n', strip=True)
                # Clean up excessive whitespace
                text = re.sub(r'\n{3,}', '\n\n', text)
                return text

        # Fallback: get body text
        body = soup.find('body')
        if body:
            for script in body(['script', 'style', 'nav', 'header', 'footer']):
                script.decompose()
            return body.get_text(separator='\n', strip=True)[:10000]

        return ""

    def _extract_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract last updated date."""
        # Try different date selectors
        selectors = [
            'meta[name="ms.date"]',
            'meta[property="article:modified_time"]',
            'time[datetime]',
            '.metadata-date',
            '.article-date'
        ]

        for selector in selectors:
            element = soup.select_one(selector)
            if element:
                if element.name == 'meta':
                    return element.get('content')
                elif element.name == 'time':
                    return element.get('datetime')
                return element.get_text(strip=True)

        return None

    def _extract_applies_to(self, soup: BeautifulSoup) -> list[str]:
        """Extract 'applies to' information."""
        applies_to = []

        # Look for applies-to sections
        selectors = ['.applies-to', '#applies-to', 'meta[name="ms.prod"]']

        for selector in selectors:
            elements = soup.select(selector)
            for element in elements:
                if element.name == 'meta':
                    applies_to.append(element.get('content', ''))
                else:
                    applies_to.append(element.get_text(strip=True))

        return applies_to

    def _extract_prerequisites(self, soup: BeautifulSoup) -> list[str]:
        """Extract prerequisites section."""
        prerequisites = []

        # Look for prerequisites heading and following list
        for heading in soup.find_all(['h2', 'h3']):
            if 'prerequisite' in heading.get_text().lower():
                next_elem = heading.find_next_sibling()
                if next_elem and next_elem.name in ['ul', 'ol']:
                    for li in next_elem.find_all('li'):
                        prerequisites.append(li.get_text(strip=True))

        return prerequisites

    def _extract_steps(self, soup: BeautifulSoup) -> list[str]:
        """Extract numbered steps from article."""
        steps = []

        # Look for ordered lists in main content
        for ol in soup.find_all('ol'):
            for li in ol.find_all('li', recursive=False):
                step_text = li.get_text(strip=True)
                if len(step_text) > 10:  # Filter out very short items
                    steps.append(step_text)

        return steps[:20]  # Limit to first 20 steps

    def _determine_article_type(self, soup: BeautifulSoup, content: str) -> str:
        """Determine the type of article."""
        content_lower = content.lower()

        # Check for troubleshooting indicators
        troubleshooting_terms = ['troubleshoot', 'fix', 'resolve', 'error', 'issue', 'problem']
        if any(term in content_lower for term in troubleshooting_terms):
            return "troubleshooting"

        # Check for how-to indicators
        howto_terms = ['how to', 'steps to', 'guide', 'set up', 'configure']
        if any(term in content_lower for term in howto_terms):
            return "how-to"

        # Check for reference documentation
        if 'reference' in content_lower or 'api' in content_lower:
            return "reference"

        # Check for tutorial
        if 'tutorial' in content_lower or 'learn' in content_lower:
            return "tutorial"

        return "unknown"

    def fetch_multiple(self, urls: list[str]) -> list[Article]:
        """
        Fetch multiple articles.

        Args:
            urls: List of article URLs

        Returns:
            List of Article objects
        """
        return [self.fetch(url) for url in urls]

    def clear_cache(self):
        """Clear the article cache."""
        self._cache.clear()
        self._cache_timestamps.clear()
