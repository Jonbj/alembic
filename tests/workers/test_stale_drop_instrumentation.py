"""#149: record what the sentiment worker discards as stale, so the loss is
measurable instead of inferred. Pure-function tests — no Redis, no DB.

The worker skips stale queue items without an LLM call and leaves them in
news:processing to be deleted at run end. Nothing is persisted, so a day that
loses 71% of its queued items looks identical to a quiet day. These helpers turn
each discarded item into a row that answers the two questions the fix depends on:
how old was it when it died, and which article was it a fan-out copy of.
"""
from datetime import datetime, timedelta, timezone

import pytest

from src.workers.sentiment import article_id_of, build_stale_drop_row

NOW = datetime(2026, 7, 27, 20, 0, tzinfo=timezone.utc)


class _Item:
    """Minimal stand-in for NewsItem — the helpers must not need the model."""

    def __init__(self, id, timestamp, source="alpaca_benzinga", asset_tags=None, title=""):
        self.id = id
        self.timestamp = timestamp
        self.source = source
        self.asset_tags = asset_tags if asset_tags is not None else []
        self.title = title


# --- article_id_of ---------------------------------------------------------

def test_strips_the_ticker_suffix_so_fan_out_copies_group_together():
    # The same article queued for 3 tickers must collapse to one article id —
    # that grouping is what makes fan-out visible.
    ids = [
        article_id_of("alpaca:60706041:JBS"),
        article_id_of("alpaca:60706041:MU"),
        article_id_of("alpaca:60706041:NVDA"),
    ]
    assert ids == ["alpaca:60706041"] * 3


def test_id_without_a_ticker_suffix_is_returned_unchanged():
    assert article_id_of("gdelt-12345") == "gdelt-12345"


def test_id_with_extra_colons_keeps_everything_but_the_last_segment():
    assert article_id_of("src:sub:12345:AAPL") == "src:sub:12345"


def test_empty_id_does_not_raise():
    assert article_id_of("") == ""


# --- build_stale_drop_row --------------------------------------------------

def test_row_carries_age_at_discard_not_age_now():
    """The age must be frozen at the moment of the drop — reconstructing it
    later from `dropped_at` would silently drift with query time."""
    item = _Item("alpaca:1:AAPL", NOW - timedelta(hours=3, minutes=30))
    row = build_stale_drop_row(item, NOW)
    assert row["age_hours"] == pytest.approx(3.5, abs=1e-6)


def test_row_groups_by_article_and_keeps_the_symbol():
    item = _Item("alpaca:60706041:MU", NOW - timedelta(hours=2), asset_tags=["MU"])
    row = build_stale_drop_row(item, NOW)
    assert row["article_id"] == "alpaca:60706041"
    assert row["item_id"] == "alpaca:60706041:MU"
    assert row["symbol"] == "MU"


def test_naive_timestamp_is_treated_as_utc():
    """Queue payloads have been seen with naive timestamps; a naive value must
    not produce a negative or absurd age."""
    item = _Item("a:1:X", datetime(2026, 7, 27, 18, 0))  # no tzinfo
    row = build_stale_drop_row(item, NOW)
    assert row["age_hours"] == pytest.approx(2.0, abs=1e-6)
    assert row["published_at"].tzinfo is not None


def test_missing_asset_tags_gives_null_symbol_not_a_crash():
    row = build_stale_drop_row(_Item("a:1", NOW - timedelta(hours=1)), NOW)
    assert row["symbol"] is None


def test_title_is_truncated_so_one_row_cannot_be_unbounded():
    long_title = "x" * 1000
    row = build_stale_drop_row(_Item("a:1:X", NOW, title=long_title), NOW)
    assert len(row["title"]) <= 300


def test_source_is_preserved_for_per_source_attribution():
    item = _Item("g:1:X", NOW - timedelta(hours=1), source="gdelt_gkg")
    assert build_stale_drop_row(item, NOW)["source"] == "gdelt_gkg"
