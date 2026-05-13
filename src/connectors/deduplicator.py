"""Redis hash-based deduplicator for news items."""

import hashlib
import unicodedata

from redis import Redis

from src.models.news import NewsItem

_DEDUP_TTL_SECONDS = 2 * 3600  # 2 hours


def compute_dedup_hash(item: NewsItem) -> str:
    """Compute SHA-256 hash of normalized title+body for deduplication.

    Args:
        item: NewsItem to hash

    Returns:
        Hex-encoded SHA-256 hash of normalized title|body
    """
    norm_title = unicodedata.normalize("NFKC", item.title).lower().strip()
    norm_body = unicodedata.normalize("NFKC", item.body[:500]).lower().strip()
    return hashlib.sha256(f"{norm_title}|{norm_body}".encode()).hexdigest()


class Deduplicator:
    """Redis-based deduplicator using SET NX with TTL.

    Uses a Redis hash with 2-hour TTL to track seen news items.
    """

    def __init__(self, redis: Redis):
        """Initialize deduplicator with Redis client.

        Args:
            redis: Redis client instance
        """
        self._r = redis

    def is_duplicate(self, item: NewsItem) -> bool:
        """Check if item is a duplicate.

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

        Used by the ingestion worker for multi-ticker deduplication:
        two items from the same article but different tickers have the
        same title+body hash but different IDs, so is_duplicate() would
        incorrectly drop the second. This method deduplicates by ID instead.
        """
        key = f"dedup:id:{hashlib.sha256(item.id.encode()).hexdigest()}"
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None

