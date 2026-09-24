"""Redis hash-based deduplicator for news items.

Provides two deduplication strategies:
  1. `is_duplicate(item)` — deduplicates by content hash (title+body).
     Used by the SentimentWorker to avoid re-processing the same article text.
  2. `is_duplicate_by_id(item)` — deduplicates by item.id.
     Used by the NewsIngestionWorker for multi-ticker articles where the same
     article text appears for multiple tickers, but each (url, ticker) pair
     should be treated as a distinct item.

Both strategies use Redis SET with NX (set if not exists) and a 4-hour TTL.
This is lightweight and avoids a separate lookup-before-write round-trip.
"""

import hashlib
import unicodedata

from redis import Redis

from src.models.news import NewsItem

_DEDUP_TTL_SECONDS = 4 * 3600  # 4 hours


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

    Uses a Redis hash with a 4-hour TTL (`_DEDUP_TTL_SECONDS`) to track seen items.
    The TTL is intentionally short because:
      - Financial news is time-sensitive; re-processing an article from hours
        ago would be stale anyway.
      - Keeps Redis memory footprint bounded.

    The docstrings here said "2 hours" from the 2026-06-27 change (`731530b`) until
    2026-09-21: whoever read the module read the opposite of the constant. The value
    itself is still 4h, i.e. TWICE `MAX_NEWS_AGE_HOURS` (=2). That mismatch makes a
    WebSocket-first article reappear at T+4h exactly — `SET NX` never refreshes the
    TTL — and the freshness gate then kills it for being stale by construction, which
    is what the `already_stale_at_fetch` cohort actually measures. Alpha cost is zero
    (every affected article had already been seen fresh within 15 minutes; the drop is
    the SECOND delivery), so the alignment 4h -> `MAX_NEWS_AGE_HOURS` is NOT exempt
    from the tuning freeze: it is pre-registered for 2026-09-28 in
    `docs/evidence/OBSERVATION_CHARTER.md` (perimeter, expected verification and
    falsification condition are stated there), because the TTL governs which news
    enters the observed coverage series (#508/#511). Do not change the constant early.
    """

    def __init__(self, redis: Redis):
        """Initialize deduplicator with Redis client.

        Args:
            redis: Redis client instance
        """
        self._r = redis

    def is_duplicate(self, item: NewsItem) -> bool:
        """Check if item is a duplicate by content hash.

        Uses SET NX (set if not exists) with the module TTL (4h; see the class
        docstring for why it is not yet aligned to MAX_NEWS_AGE_HOURS). Returns True
        if the item was already seen (SET NX failed), False if first occurrence.

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
        earnings") generates two NewsItem objects with the SAME title and body but
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

    def is_duplicate_content_symbol(self, item: NewsItem) -> bool:
        """Cross-source dedup: content hash + primary ticker (EN-03).

        The same article fetched from two sources has different ids
        (`is_duplicate_by_id` misses it) but identical normalised text.
        Keying on content hash ALONE would break multi-ticker fan-out
        (same text, different ticker → legitimate distinct items), so the
        key includes the item's primary ticker.

        Items without asset_tags are never treated as content duplicates
        (nothing downstream to save; discarding here would hide data).
        """
        if not item.asset_tags:
            return False
        key = f"dedup:content:{compute_dedup_hash(item)}:{item.asset_tags[0]}"
        result = self._r.set(key, 1, ex=_DEDUP_TTL_SECONDS, nx=True)
        return result is None
