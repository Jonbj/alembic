"""FIX-06: every explicit sentiment pre-filter leaves structured evidence."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, call

from src.models.news import MarketAuxNewsItem, NewsItem
from src.workers.sentiment import (
    _filter_neutral_items,
    _persist_sentiment_discards,
    build_parse_failure_drop_row,
)


def _item(*, sentiment: float | None = None):
    cls = MarketAuxNewsItem if sentiment is not None else NewsItem
    kwargs = {"marketaux_sentiment": sentiment} if sentiment is not None else {}
    return cls(
        id="marketaux:1:AAPL",
        source="marketaux",
        timestamp=datetime(2026, 8, 16, tzinfo=timezone.utc),
        title="Article",
        body="Body",
        url="https://example.com/1",
        asset_tags=["AAPL"],
        **kwargs,
    )


def test_near_neutral_prefilter_records_reason():
    rows = []

    kept, skipped = _filter_neutral_items(
        [_item(sentiment=0.1), _item(sentiment=0.8), _item()],
        discard_rows=rows,
    )

    assert skipped == 1
    assert len(kept) == 2
    assert rows[0]["discarded_reason"] == "near_neutral"
    assert rows[0]["discard_stage"] == "sentiment"


def test_unparseable_queue_payload_gets_stable_parse_failure_id():
    first = build_parse_failure_drop_row(b'{"broken"')
    second = build_parse_failure_drop_row(b'{"broken"')

    assert first["discarded_reason"] == "parse_fail"
    assert first["discard_stage"] == "sentiment"
    assert first["item_id"] == second["item_id"]
    assert first["item_id"].startswith("unparseable:")


def test_stale_and_parse_fail_counts_reach_source_funnel():
    store = MagicMock()
    rows = [
        {"source": "gdelt_gkg", "discarded_reason": "stale"},
        {"source": "gdelt_gkg", "discarded_reason": "stale"},
        {"source": "unknown", "discarded_reason": "parse_fail"},
        {"source": "marketaux", "discarded_reason": "near_neutral"},
    ]

    _persist_sentiment_discards(store, rows)

    store.record_news_discards.assert_called_once_with(rows)
    assert store.record_ingestion_stats.call_args_list == [
        call("gdelt_gkg", {"discarded_stale": 2}),
        call("unknown", {"parse_fail": 1}),
    ]
