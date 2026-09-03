"""#433: publication-to-ingestion latency must be measured without fan-out bias."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts.characterize_news_ingestion_latency import (
    FETCH_OBSERVATIONS_SQL,
    summarize_alpaca_polls,
    summarize_first_seen,
    summarize_stale_drops,
)


def _ts(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, second, tzinfo=timezone.utc)


def _observation(
    article_key: str,
    published_at: datetime,
    raw_ingested_at: datetime,
    *,
    source: str = "alpaca_benzinga",
) -> dict:
    return {
        "source": source,
        "article_key": article_key,
        "published_at": published_at,
        "raw_ingested_at": raw_ingested_at,
        "ledger": "drop",
        "discarded_reason": "duplicate_id",
    }


def test_first_seen_distribution_deduplicates_ticker_fanout_and_repeated_polls():
    rows = [
        _observation("article-a", _ts(28, 13, 30), _ts(28, 14, 0, 1)),
        # The same provider article fans out to another ticker in the same fetch.
        _observation("article-a", _ts(28, 13, 30), _ts(28, 14, 0, 2)),
        # It is returned again by the overlapping latest-page poll.
        _observation("article-a", _ts(28, 13, 30), _ts(28, 14, 15, 1)),
        _observation("article-b", _ts(28, 10, 0), _ts(28, 14, 0, 1)),
        _observation(
            "gkg-a", _ts(28, 14, 15), _ts(28, 14, 15, 1), source="gdelt_gkg"
        ),
    ]

    source_rows, hourly_rows = summarize_first_seen(rows, stale_hours=2.0)

    alpaca = next(row for row in source_rows if row["source"] == "alpaca_benzinga")
    assert alpaca == {
        "source": "alpaca_benzinga",
        "articles": 2,
        "p50_hours": pytest.approx(2.25),
        "p75_hours": pytest.approx(3.125),
        "p95_hours": pytest.approx(3.825),
        "born_stale": 1,
        "born_stale_pct": pytest.approx(50.0),
        "negative_latency": 0,
    }
    assert [row["articles"] for row in hourly_rows] == [2, 1]


def test_stale_drop_summary_keeps_queue_item_denominator():
    rows = [
        {
            "source": "alpaca_benzinga",
            "dropped_at": _ts(28, 14, 15),
            "published_at": _ts(28, 10, 0),
            "raw_ingested_at": _ts(28, 14, 0),
        },
        # Same article, second ticker: this is a second consumed queue slot.
        {
            "source": "alpaca_benzinga",
            "dropped_at": _ts(28, 14, 30),
            "published_at": _ts(28, 10, 0),
            "raw_ingested_at": _ts(28, 14, 0),
        },
        {
            "source": "alpaca_benzinga",
            "dropped_at": _ts(28, 14, 30),
            "published_at": _ts(28, 13, 0),
            "raw_ingested_at": _ts(28, 14, 0),
        },
    ]

    summary = summarize_stale_drops(rows, stale_hours=2.0)

    assert summary == [
        {
            "session": "2026-08-28",
            "source": "alpaca_benzinga",
            "stale_drops": 3,
            "fetch_latency_hours": pytest.approx(3.0),
            "queue_wait_hours": pytest.approx(1 / 3),
            "born_stale": 2,
            "born_stale_pct": pytest.approx(200 / 3),
        }
    ]


def test_alpaca_poll_summary_measures_cadence_overlap_and_page_edge():
    rows = [
        _observation("old", _ts(28, 10, 0), _ts(28, 14, 0, 1)),
        _observation("recent", _ts(28, 13, 50), _ts(28, 14, 0, 1)),
        _observation("old", _ts(28, 10, 0), _ts(28, 14, 15, 1)),
        _observation("recent", _ts(28, 13, 50), _ts(28, 14, 15, 1)),
        _observation("new", _ts(28, 14, 10), _ts(28, 14, 15, 1)),
    ]

    summary, cycles = summarize_alpaca_polls(rows, stale_hours=2.0)

    assert summary["cycles"] == 2
    assert summary["p50_intraday_interval_minutes"] == pytest.approx(15.0)
    assert summary["p95_intraday_interval_minutes"] == pytest.approx(15.0)
    assert summary["max_intraday_interval_minutes"] == pytest.approx(15.0)
    assert summary["intraday_gaps_over_20_minutes"] == 0
    assert summary["publication_window_overlaps"] == 1
    assert summary["publication_window_gaps"] == 0
    assert summary["high_latency_first_seen"] == 1
    assert summary["high_latency_first_seen_at_14_utc"] == 1
    assert summary["high_latency_at_14_pct"] == pytest.approx(100.0)
    assert summary["high_latency_median_page_percentile"] == pytest.approx(1.0)
    assert summary["high_latency_in_oldest_quartile"] == 1
    assert cycles[0]["articles"] == 2
    assert cycles[1]["articles"] == 3


def test_observation_query_covers_processed_and_discarded_ledgers():
    normalized = " ".join(FETCH_OBSERVATIONS_SQL.lower().split())

    assert "from news_log" in normalized
    assert "from news_queue_drops" in normalized
    assert "raw_ingested_at >= %s" in normalized
    assert "raw_ingested_at < %s" in normalized
    assert "article_key" in normalized
