"""EN-05: NewsItem carries the connector fetch time through the Redis queue,
so news_log can record real per-source latency (fetch vs published vs processed)."""

from datetime import datetime, timezone

from src.models.news import NewsItem


def test_raw_ingested_at_defaults_to_none():
    item = NewsItem(id="u:AAPL", body="b")
    assert item.raw_ingested_at is None


def test_raw_ingested_at_survives_json_roundtrip():
    ts = datetime(2026, 7, 3, 15, 0, tzinfo=timezone.utc)
    item = NewsItem(id="u:AAPL", body="b", raw_ingested_at=ts)
    restored = NewsItem.model_validate_json(item.model_dump_json())
    assert restored.raw_ingested_at == ts


def test_old_queue_payload_without_field_still_parses():
    """Items already in the queue at deploy time lack the field — must not crash."""
    restored = NewsItem.model_validate_json('{"id": "u:AAPL", "body": "b"}')
    assert restored.raw_ingested_at is None
