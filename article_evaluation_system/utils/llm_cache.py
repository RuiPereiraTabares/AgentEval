"""
LLM response deduplication cache.

Caches successful, non-refused LLM responses keyed by
SHA-256(system_prompt + "\\0" + user_message).

Cache hits are most frequent for:
- Repeat runs over the same input CSV (crash-recovery, format changes)
- Cases that cite the same article URL when the user_message structure
  makes the prompts identical across cases (e.g. same article + same issue
  category in mweaeval mode)

The cache is backed by SQLite with WAL mode so it is safe to use from
multiple concurrent threads.
"""

import hashlib
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_LLM_CACHE_DB: str = str(Path.home() / ".llm_response_cache.db")
_LLM_CACHE_TTL: int = 7 * 24 * 3600  # 7 days


class LLMResponseCache:
    """SQLite-backed LLM response cache (thread-safe).

    Only successful (non-refused) responses from attempt 0 (the original,
    un-rephrased prompt) are stored.  This avoids caching RAI-rephrase
    variants whose keys are less useful to reuse.
    """

    def __init__(self, db_path: str = _LLM_CACHE_DB, ttl: int = _LLM_CACHE_TTL) -> None:
        self._ttl = ttl
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                cache_key  TEXT PRIMARY KEY,
                response   TEXT NOT NULL,
                cached_at  REAL NOT NULL
            )
        """)
        self._conn.commit()
        logger.debug(f"[LLMCache] SQLite cache opened: {db_path}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, system_prompt: str, user_message: str) -> Optional[str]:
        """Return cached response or ``None`` if absent / expired."""
        key = self._make_key(system_prompt, user_message)
        with self._lock:
            row = self._conn.execute(
                "SELECT response, cached_at FROM llm_cache WHERE cache_key=?", (key,)
            ).fetchone()
        if row is None:
            return None
        response, cached_at = row
        if time.time() - cached_at > self._ttl:
            logger.debug(f"[LLMCache] Expired key={key[:12]}")
            return None
        logger.debug(f"[LLMCache] Hit key={key[:12]}")
        return response

    def put(self, system_prompt: str, user_message: str, response: str) -> None:
        """Store a response in the cache."""
        key = self._make_key(system_prompt, user_message)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache (cache_key, response, cached_at) "
                "VALUES (?, ?, ?)",
                (key, response, time.time()),
            )
            self._conn.commit()
        logger.debug(f"[LLMCache] Stored key={key[:12]}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(system_prompt: str, user_message: str) -> str:
        combined = system_prompt + "\x00" + user_message
        return hashlib.sha256(combined.encode("utf-8", errors="replace")).hexdigest()


# Module-level singleton — shared across all agents and threads
_llm_cache = LLMResponseCache()
