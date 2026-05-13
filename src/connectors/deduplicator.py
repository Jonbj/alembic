"""Redis hash-based deduplicator for news items.

Provides two deduplication strategies:
  1. `is_duplicate(item)` — deduplicates by content hash (title+body).
     Used by the SentimentWorker to avoid re-processing the same article text.
  2. `is_duplicate_by_id(item)` — deduplicates by item.id.
     Used by the NewsIngestionWorker for multi-ticker articles where the same
     article text appears for multiple tickers, but each (url, ticker) pair
     should be treated as a distinct item.

Both strategies use Redis SET with NX (set if not exists) and a 2-hour TTL.
This is lightweight and avoids a separate lookup-before-write round-trip.
"""

import hashlib
import unicodedata

from redis import Redis

from src.models.news import NewsItem

_DEDUP_TTL_SECONDS = 2 * 3600  # 2 hours


def compute_dedup_hash(item: NewsItem) -> str:
    """Compute SHA-256 hash of normalized title+body for deduplication.

    Normalisation steps:
      1. NFKC Unicode normalisation (handles homoglyphs, accents, etc.).
      2. Lowercase.
      3. Strip leading/trailing whitespace.
      4. Body is truncated to 500 chars to keep hash computation fast.

    The hash is deterministic for identical content, even if the original
    text has different Unicode representations.

    Args:
        item: NewsItem to hash

    Returns:
        Hex-encoded SHA-256 hash of "{normalised_title}|{normalised_body}".
    """
    norm_title = unicodedata.normalize("NFKC", item.title).lower().strip()
    norm_body = unicodedata.normalize("NFKC", item.body[:500]).lower().strip()
    return hashlib.sha256(f"{norm_title}|{norm_body}".encode()).hexdigest()


class Deduplicator:
    """Redis-based deduplicator using SET NX with TTL.

    Uses a Redis hash with 2-hour TTL to track seen news items.
    The TTL is intentionally short (2h) because:
      - Financial news is time-sensitive; re-processing an article from 3 hours
        ago would be stale anyway.
      - Keeps Redis memory footprint bounded.
    """

    def __init__(self, redis: Redis):
        """Initialize deduplicator with Redis client.

        Args:
            redis: Redis client instance
        """
        self._r = redis

    def is_duplicate(self, item: NewsItem) -> bool:
        """Check if item is a duplicate by content hash.

        Uses SET NX (set if not exists) with 2h TTL. Returns True if
        the item was already seen (SET NX failed), False if first occurrence.

        Args:
            item: NewsItem to check

        Returns:
            True if duplicate (already seen), False if first occurrence
        """
        key = f"dedup:{compute_dedup_hash(item)}"
        # SET NX returns True on first insert, None if key exists
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None

    def is_duplicate_by_id(self, item: NewsItem) -> bool:
        """Check if item is a duplicate by item.id.

        **Why this method exists:**
        In the news-driven pipeline, a single article (e.g. "Apple and Microsoft
ernings") generates two NewsItem objects with the SAME title and body but
        DIFFERENT ids ("url:AAPL" and "url:MSFT"). `is_duplicate()` would see
        the identical content hash and incorrectly drop the second item.

        This method deduplicates by the composite id instead, ensuring that
        each (url, ticker) pair is processed exactly once while allowing the
        same article to produce separate signals for different tickers.

        Args:
            item: NewsItem to check (id must be set, preferably composite).

        Returns:
            True if duplicate (already seen), False if first occurrence.
        """
        key = f"dedup:id:{hashlib.sha256(item.id.encode()).hexdigest()}"
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None
