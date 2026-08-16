"""Structured evidence for news discarded before sentiment scoring."""

from datetime import datetime, timezone

from src.connectors.deduplicator import compute_dedup_hash


DISCARD_REASONS = frozenset(
    {
        "no_ticker",
        "stale",
        "duplicate_id",
        "duplicate_content",
        "not_tradable",
        "parse_fail",
        "near_neutral",
    }
)
DISCARD_STAGES = frozenset({"ingestion", "sentiment"})


def article_id_of(item_id: str) -> str:
    """Collapse a per-ticker queue id to the source article id."""
    if ":" not in item_id:
        return item_id
    return item_id.rsplit(":", 1)[0]


def build_news_discard_row(
    item,
    *,
    reason: str,
    stage: str,
    symbol: str | None = None,
    discarded_at: datetime | None = None,
) -> dict:
    """Build one bounded, persistable discard event from a news-like item."""
    if reason not in DISCARD_REASONS:
        raise ValueError(f"Unknown news discard reason: {reason}")
    if stage not in DISCARD_STAGES:
        raise ValueError(f"Unknown news discard stage: {stage}")

    now = discarded_at or datetime.now(timezone.utc)
    tags = getattr(item, "asset_tags", None) or []
    resolved_symbol = symbol if symbol is not None else (tags[0] if tags else None)
    try:
        content_hash = compute_dedup_hash(item)
    except Exception:
        content_hash = None

    item_id = str(getattr(item, "id", "") or "")
    return {
        "item_id": item_id,
        "article_id": article_id_of(item_id),
        "symbol": resolved_symbol,
        "source": str(getattr(item, "source", "") or ""),
        "published_at": getattr(item, "timestamp", None),
        "age_hours": None,
        "title": str(getattr(item, "title", "") or "")[:300],
        "url": str(getattr(item, "url", "") or "")[:1000],
        "raw_ingested_at": getattr(item, "raw_ingested_at", None) or now,
        "content_hash": content_hash,
        "discarded_reason": reason,
        "discard_stage": stage,
    }
