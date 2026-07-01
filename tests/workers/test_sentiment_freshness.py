"""Worker skips stale news without an LLM call (drains backlog, avoids stale signals)."""
from datetime import datetime, timedelta, timezone

from src.models.news import NewsItem
from src.workers.sentiment import _SENTIMENT_MAX_NEWS_AGE_HOURS as _MAX, _is_stale_news

_NOW = datetime(2026, 6, 30, 20, 0, tzinfo=timezone.utc)


def _item(ts):
    return NewsItem(id="x", body="b", title="t", timestamp=ts)


def test_fresh_news_not_stale():
    assert _is_stale_news(_item(_NOW - timedelta(hours=1)), _NOW) is False


def test_old_news_is_stale():
    # Comfortably past any sane threshold (cross-session leftover).
    assert _is_stale_news(_item(_NOW - timedelta(hours=_MAX + 6)), _NOW) is True


def test_boundary_around_threshold():
    # Just under the configured threshold is fresh; just over is stale.
    assert _is_stale_news(_item(_NOW - timedelta(hours=_MAX) + timedelta(minutes=1)), _NOW) is False
    assert _is_stale_news(_item(_NOW - timedelta(hours=_MAX) - timedelta(minutes=1)), _NOW) is True


def test_naive_timestamp_treated_as_utc():
    # 13-day-old, tz-naive (as seen in the queue backlog) → stale, no crash.
    assert _is_stale_news(_item(datetime(2026, 6, 17, 12, 0)), _NOW) is True


def test_custom_threshold():
    assert _is_stale_news(_item(_NOW - timedelta(hours=5)), _NOW, max_age_hours=4) is True
    assert _is_stale_news(_item(_NOW - timedelta(hours=3)), _NOW, max_age_hours=4) is False
